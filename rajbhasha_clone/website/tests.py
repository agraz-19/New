import json
from datetime import date
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from .models import (
    CustomUser, EditRequest, MonthlyFill, MonthlySnapshot, QPRRecord, QuarterlyFill,
    QuarterlySnapshot, Role, Section11SpecificAchievementsData, WeeklyFill, WeeklySnapshot
)
from .views import (
    _aggregate_section11_text_for_range, _rebuild_monthly_snapshot_from_source,
    is_period_overlapping, qpr_form, qpr_save_record, report_detail, report_list,
    request_qpr_edit
)


class QPROverlapRestrictionTests(TestCase):
    def setUp(self):
        Role.objects.get_or_create(name='user')
        self.user = CustomUser.objects.create_user(
            username='overlap-user',
            email='overlap@example.com',
            password='password123'
        )
        self.factory = RequestFactory()

    def _record(self, frequency, start, end):
        return QPRRecord.objects.create(
            user=self.user,
            officeName='Office',
            officeCode='OFF',
            region='Region A',
            quarter='Apr-Jun',
            year='2026-2027',
            frequency=frequency,
            period_start=start,
            period_end=end,
            status='Submitted',
            is_submitted=True,
        )

    def test_daily_is_blocked_by_submitted_weekly_monthly_or_quarterly_coverage(self):
        self._record('weekly', date(2026, 4, 6), date(2026, 4, 11))
        self.assertTrue(is_period_overlapping(self.user, date(2026, 4, 7), date(2026, 4, 7), new_frequency='daily'))

        QPRRecord.objects.all().delete()
        self._record('monthly', date(2026, 4, 1), date(2026, 4, 30))
        self.assertTrue(is_period_overlapping(self.user, date(2026, 4, 7), date(2026, 4, 7), new_frequency='daily'))

        QPRRecord.objects.all().delete()
        self._record('quarterly', date(2026, 4, 1), date(2026, 6, 30))
        self.assertTrue(is_period_overlapping(self.user, date(2026, 4, 7), date(2026, 4, 7), new_frequency='daily'))

    def test_weekly_is_blocked_by_submitted_monthly_or_quarterly_coverage(self):
        self._record('monthly', date(2026, 4, 1), date(2026, 4, 30))
        self.assertTrue(is_period_overlapping(self.user, date(2026, 4, 6), date(2026, 4, 11), new_frequency='weekly'))

        QPRRecord.objects.all().delete()
        self._record('quarterly', date(2026, 4, 1), date(2026, 6, 30))
        self.assertTrue(is_period_overlapping(self.user, date(2026, 4, 6), date(2026, 4, 11), new_frequency='weekly'))

    def test_monthly_is_blocked_by_submitted_quarterly_coverage(self):
        self._record('quarterly', date(2026, 4, 1), date(2026, 6, 30))
        self.assertTrue(is_period_overlapping(self.user, date(2026, 4, 1), date(2026, 4, 30), new_frequency='monthly'))

    def test_aggregate_frequencies_can_still_be_submitted_over_lower_level_sources(self):
        self._record('daily', date(2026, 4, 6), date(2026, 4, 6))
        self.assertFalse(is_period_overlapping(self.user, date(2026, 4, 1), date(2026, 4, 30), new_frequency='monthly'))

        self._record('monthly', date(2026, 4, 1), date(2026, 4, 30))
        self.assertFalse(is_period_overlapping(self.user, date(2026, 4, 1), date(2026, 6, 30), new_frequency='quarterly'))

    def test_blank_frequency_defaults_to_daily_instead_of_rejecting_frequency_required(self):
        request = self.factory.post('/qpr/records/save/', {
            'status': 'Submitted',
            'officeName': 'Office',
            'officeCode': 'OFF',
            'region': 'Region A',
            'quarter': '30 जून / Jun 30',
            'year': '2026-2027',
            'frequency': '',
            'selected_date': '2026-04-06',
            'details': '{}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        qpr_save_record.__wrapped__(request)

        messages = [str(message) for message in get_messages(request)]
        self.assertNotIn('Frequency is required', messages)
        self.assertTrue(QPRRecord.objects.filter(user=self.user, frequency='daily').exists())

    def test_duplicate_covered_submission_redirects_back_to_qpr_form_with_popup_message(self):
        self._record('monthly', date(2026, 4, 1), date(2026, 4, 30))
        request = self.factory.post('/qpr/records/save/', {
            'status': 'Submitted',
            'officeName': 'Office',
            'officeCode': 'OFF',
            'region': 'Region A',
            'quarter': '30 जून / Jun 30',
            'year': '2026-2027',
            'frequency': 'daily',
            'selected_date': '2026-04-06',
            'details': '{}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/qpr/form/')
        self.assertEqual(request.session['qpr_popup_error'], 'This QPR has already been filled for the selected period.')

    def test_section11_cumulative_text_includes_weekly_monthly_and_quarterly_entries(self):
        daily = self._record('daily', date(2026, 4, 6), date(2026, 4, 6))
        weekly = self._record('weekly', date(2026, 4, 6), date(2026, 4, 11))
        monthly = self._record('monthly', date(2026, 4, 1), date(2026, 4, 30))
        quarterly = self._record('quarterly', date(2026, 4, 1), date(2026, 6, 30))

        Section11SpecificAchievementsData.objects.create(qpr_record=daily, innovative_work='Daily text')
        Section11SpecificAchievementsData.objects.create(qpr_record=weekly, innovative_work='Weekly text')
        Section11SpecificAchievementsData.objects.create(qpr_record=monthly, innovative_work='Monthly text')
        Section11SpecificAchievementsData.objects.create(qpr_record=quarterly, innovative_work='Quarterly text')

        text = _aggregate_section11_text_for_range(
            self.user,
            date(2026, 4, 1),
            date(2026, 6, 30),
            'innovative_work',
            source_frequency='all'
        )

        self.assertIn('Daily text', text)
        self.assertIn('Weekly text', text)
        self.assertIn('Monthly text', text)
        self.assertIn('Quarterly text', text)
        self.assertNotIn('[Daily', text)
        self.assertNotIn('[Weekly', text)
        self.assertNotIn('[Monthly', text)
        self.assertNotIn('[Quarterly', text)

    def test_approved_weekly_snapshot_edit_overwrites_snapshot_values(self):
        record = self._record('daily', date(2026, 4, 6), date(2026, 4, 6))
        WeeklySnapshot.objects.create(
            user=self.user,
            quarter=record.quarter,
            year=record.year,
            period_start=date(2026, 4, 6),
            period_end=date(2026, 4, 11),
            s2_meetings=3,
            s7_total=8,
        )
        EditRequest.objects.create(
            user=self.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            requested_data={'edit_scope': 'weekly'},
            status='approved',
        )
        request = self.factory.post('/qpr/records/save/', {
            'id': str(record.pk),
            'status': 'Submitted',
            'snapshot_edit_scope': 'weekly',
            'details': '{"s2_meetings": "11", "s7_total": "22"}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)

        snapshot = WeeklySnapshot.objects.get(user=self.user, period_start=date(2026, 4, 6), period_end=date(2026, 4, 11))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(snapshot.s2_meetings, 11)
        self.assertEqual(snapshot.s7_total, 22)
        self.assertTrue(snapshot.is_overwritten)
        self.assertTrue(EditRequest.objects.filter(qpr_record_id=record.pk, status='temp use').exists())

    def test_weekly_snapshot_edit_is_not_reset_by_parent_refresh(self):
        record = self._record('weekly', date(2026, 4, 6), date(2026, 4, 11))
        WeeklyFill.objects.create(
            user=self.user,
            quarter=record.quarter,
            year=record.year,
            period_start=date(2026, 4, 6),
            period_end=date(2026, 4, 11),
            s2_meetings=6,
        )
        WeeklySnapshot.objects.create(
            user=self.user,
            quarter=record.quarter,
            year=record.year,
            period_start=date(2026, 4, 6),
            period_end=date(2026, 4, 11),
            s2_meetings=6,
        )
        EditRequest.objects.create(
            user=self.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            requested_data={'edit_scope': 'weekly'},
            status='approved',
        )
        request = self.factory.post('/qpr/records/save/', {
            'id': str(record.pk),
            'status': 'Submitted',
            'snapshot_edit_scope': 'weekly',
            'details': '{"s2_meetings": "9"}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)

        snapshot = WeeklySnapshot.objects.get(user=self.user, period_start=date(2026, 4, 6), period_end=date(2026, 4, 11))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(snapshot.s2_meetings, 9)
        self.assertTrue(snapshot.is_overwritten)

    def test_monthly_snapshot_edit_is_not_reset_by_quarterly_refresh(self):
        record = self._record('monthly', date(2026, 4, 1), date(2026, 4, 30))
        MonthlyFill.objects.create(
            user=self.user,
            quarter=record.quarter,
            year=record.year,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            s2_meetings=6,
        )
        MonthlySnapshot.objects.create(
            user=self.user,
            quarter=record.quarter,
            year=record.year,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            s2_meetings=6,
        )
        EditRequest.objects.create(
            user=self.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            requested_data={'edit_scope': 'monthly'},
            status='approved',
        )
        request = self.factory.post('/qpr/records/save/', {
            'id': str(record.pk),
            'status': 'Submitted',
            'snapshot_edit_scope': 'monthly',
            'details': '{"s2_meetings": "13"}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)

        snapshot = MonthlySnapshot.objects.get(user=self.user, period_start=date(2026, 4, 1), period_end=date(2026, 4, 30))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(snapshot.s2_meetings, 13)
        self.assertTrue(snapshot.is_overwritten)

    def test_quarterly_snapshot_edit_overwrites_snapshot_values(self):
        record = self._record('quarterly', date(2026, 4, 1), date(2026, 6, 30))
        QuarterlyFill.objects.create(
            user=self.user,
            quarter=record.quarter,
            year=record.year,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            s2_meetings=6,
        )
        QuarterlySnapshot.objects.create(
            user=self.user,
            quarter=record.quarter,
            year=record.year,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            s2_meetings=6,
        )
        EditRequest.objects.create(
            user=self.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            requested_data={'edit_scope': 'quarterly'},
            status='approved',
        )
        request = self.factory.post('/qpr/records/save/', {
            'id': str(record.pk),
            'status': 'Submitted',
            'snapshot_edit_scope': 'quarterly',
            'details': '{"s2_meetings": "21"}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)

        snapshot = QuarterlySnapshot.objects.get(user=self.user, quarter=record.quarter, year=record.year)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(snapshot.s2_meetings, 21)
        self.assertTrue(snapshot.is_overwritten)

    def test_weekly_entry_qpr_can_be_created_as_draft(self):
        request = self.factory.post('/qpr/records/save/', {
            'status': 'Draft',
            'officeName': 'Office',
            'officeCode': 'OFF',
            'region': 'Region A',
            'quarter': '30 जून / Jun 30',
            'year': '2026-2027',
            'frequency': 'weekly',
            'selected_date': '2026-04-06',
            'details': '{}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/qpr/reports/')
        record = QPRRecord.objects.get(user=self.user, frequency='weekly')
        self.assertEqual(record.status, 'Draft')
        self.assertFalse(record.is_submitted)
        self.assertEqual(record.period_start, date(2026, 4, 6))
        self.assertEqual(record.period_end, date(2026, 4, 11))

    def test_snapshot_overwrite_cannot_be_saved_as_draft(self):
        record = self._record('daily', date(2026, 4, 6), date(2026, 4, 6))
        WeeklySnapshot.objects.create(
            user=self.user,
            quarter=record.quarter,
            year=record.year,
            period_start=date(2026, 4, 6),
            period_end=date(2026, 4, 11),
            s2_meetings=3,
        )
        EditRequest.objects.create(
            user=self.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            requested_data={'edit_scope': 'weekly'},
            status='approved',
        )
        request = self.factory.post('/qpr/records/save/', {
            'id': str(record.pk),
            'status': 'Draft',
            'snapshot_edit_scope': 'weekly',
            'details': '{"s2_meetings": "11"}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)

        snapshot = WeeklySnapshot.objects.get(user=self.user, period_start=date(2026, 4, 6), period_end=date(2026, 4, 11))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/qpr/reports/')
        self.assertEqual(snapshot.s2_meetings, 3)
        self.assertFalse(snapshot.is_overwritten)
        self.assertTrue(EditRequest.objects.filter(qpr_record_id=record.pk, status='approved').exists())

    def test_may_daily_in_cross_month_week_does_not_leak_into_april_monthly_snapshot(self):
        request = self.factory.post('/qpr/records/save/', {
            'status': 'Submitted',
            'officeName': 'Office',
            'officeCode': 'OFF',
            'region': 'Region A',
            'quarter': '30 जून / Jun 30',
            'year': '2026-2027',
            'frequency': 'daily',
            'selected_date': '2026-05-02',
            'details': '{"s2_meetings": "7"}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)
        self.assertEqual(response.status_code, 302)

        weekly_snapshot = WeeklySnapshot.objects.get(
            user=self.user,
            period_start=date(2026, 4, 27),
            period_end=date(2026, 5, 2),
        )
        self.assertEqual(weekly_snapshot.s2_meetings, 7)

        _rebuild_monthly_snapshot_from_source(
            self.user,
            date(2026, 4, 1),
            date(2026, 4, 30),
            '30 जून / Jun 30',
            '2026-2027',
        )

        april_snapshot = MonthlySnapshot.objects.get(
            user=self.user,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
        )
        may_snapshot = MonthlySnapshot.objects.get(
            user=self.user,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
        )

        self.assertEqual(april_snapshot.s2_meetings, 0)
        self.assertEqual(may_snapshot.s2_meetings, 7)

    def test_cross_month_weekly_fill_is_cumulated_to_month_with_missing_days(self):
        for day in [27, 28, 29, 30]:
            self._record('daily', date(2026, 4, day), date(2026, 4, day))

        WeeklyFill.objects.create(
            user=self.user,
            quarter='30 जून / Jun 30',
            year='2026-2027',
            period_start=date(2026, 4, 27),
            period_end=date(2026, 5, 2),
            s2_meetings=8,
        )
        WeeklySnapshot.objects.create(
            user=self.user,
            quarter='30 जून / Jun 30',
            year='2026-2027',
            period_start=date(2026, 4, 27),
            period_end=date(2026, 5, 2),
            s2_meetings=8,
        )

        _rebuild_monthly_snapshot_from_source(
            self.user,
            date(2026, 4, 1),
            date(2026, 4, 30),
            '30 जून / Jun 30',
            '2026-2027',
        )
        _rebuild_monthly_snapshot_from_source(
            self.user,
            date(2026, 5, 1),
            date(2026, 5, 31),
            '30 जून / Jun 30',
            '2026-2027',
        )

        april_snapshot = MonthlySnapshot.objects.get(
            user=self.user,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
        )
        may_snapshot = MonthlySnapshot.objects.get(
            user=self.user,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
        )

        self.assertEqual(april_snapshot.s2_meetings, 0)
        self.assertEqual(may_snapshot.s2_meetings, 8)

    def test_scoped_edit_request_before_period_end_is_rejected(self):
        record = self._record('monthly', date(2026, 5, 1), date(2026, 5, 31))
        request = self.factory.post(f'/qpr/reports/{record.pk}/request-edit/', {
            'reason': 'Need correction',
            'edit_scope': 'monthly',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        with patch('website.views.timezone.localdate', return_value=date(2026, 5, 3)):
            response = request_qpr_edit.__wrapped__(request, record.pk)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(EditRequest.objects.filter(qpr_record_id=record.pk).exists())

    def test_overwritten_monthly_snapshot_is_not_changed_by_daily_fast_path(self):
        monthly_snapshot = MonthlySnapshot.objects.create(
            user=self.user,
            quarter='Apr-Jun',
            year='2026-2027',
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            s2_meetings=50,
            is_overwritten=True,
        )

        request = self.factory.post('/qpr/records/save/', {
            'status': 'Submitted',
            'officeName': 'Office',
            'officeCode': 'OFF',
            'region': 'Region A',
            'quarter': '30 जून / Jun 30',
            'year': '2026-2027',
            'frequency': 'daily',
            'selected_date': '2026-04-06',
            'details': '{"s2_meetings": "7"}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        qpr_save_record.__wrapped__(request)

        monthly_snapshot.refresh_from_db()
        self.assertEqual(monthly_snapshot.s2_meetings, 50)
        self.assertTrue(monthly_snapshot.is_overwritten)

    def test_scoped_weekly_approval_does_not_unlock_base_daily_qpr(self):
        record = self._record('daily', date(2026, 4, 6), date(2026, 4, 6))
        EditRequest.objects.create(
            user=self.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            requested_data={'edit_scope': 'weekly'},
            status='approved',
        )

        request = self.factory.get('/qpr/form/')
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        profile = self.user.profile
        profile.approval_status = 'approved'
        profile.save(update_fields=['approval_status'])

        with patch('website.views.render', return_value=HttpResponse('ok')) as render_mock:
            response = qpr_form.__wrapped__(request)
            context = render_mock.call_args[0][2]

        self.assertEqual(response.status_code, 200)
        records = json.loads(context['records_json'])
        preloaded = records[0]
        self.assertFalse(preloaded['can_edit'])
        self.assertTrue(preloaded['snapshot_can_edit'])
        self.assertEqual(preloaded['edit_approved_scope'], 'weekly')
        self.assertEqual(preloaded['snapshot_edit']['scope'], 'weekly')

    def test_report_list_scoped_weekly_approval_does_not_mark_daily_editable(self):
        record = self._record('daily', date(2026, 4, 6), date(2026, 4, 6))
        EditRequest.objects.create(
            user=self.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            requested_data={'edit_scope': 'weekly'},
            status='approved',
        )

        request = self.factory.get('/qpr/reports/')
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        with patch('website.views.render', return_value=HttpResponse('ok')) as render_mock:
            response = report_list.__wrapped__(request)
            context = render_mock.call_args[0][2]

        self.assertEqual(response.status_code, 200)
        records = json.loads(context['records_json'])
        preloaded = records[0]
        self.assertFalse(preloaded['can_edit'])
        self.assertTrue(preloaded['snapshot_can_edit'])
        self.assertEqual(preloaded['edit_approved_scope'], 'weekly')

    def test_report_list_monthly_fill_actions_are_only_on_first_missing_daily_row(self):
        monthly_record = QPRRecord.objects.create(
            user=self.user,
            officeName='Office',
            officeCode='OFF',
            region='Region A',
            quarter='30 जून / Jun 30',
            year='2026-2027',
            frequency='monthly',
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            status='Submitted',
            is_submitted=True,
        )
        MonthlyFill.objects.create(
            user=self.user,
            quarter='30 जून / Jun 30',
            year='2026-2027',
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            s2_meetings=5,
        )

        request = self.factory.get('/qpr/reports/')
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        with patch('website.views.render', return_value=HttpResponse('ok')) as render_mock:
            response = report_list.__wrapped__(request)
            context = render_mock.call_args[0][2]

        self.assertEqual(response.status_code, 200)
        summary = json.loads(context['summary_json'])
        may_1 = next(d for d in summary['daily'] if d['period_start'] == '2026-05-01')
        may_2 = next(d for d in summary['daily'] if d['period_start'] == '2026-05-02')
        first_week = next(w for w in summary['weekly'] if w['period_start'] == '2026-04-27')

        self.assertTrue(may_1['filled_by_monthly'])
        self.assertTrue(may_1['is_first_monthly_fill_day'])
        self.assertEqual(may_1['monthly_record_id'], monthly_record.pk)
        self.assertTrue(may_2['filled_by_monthly'])
        self.assertFalse(may_2['is_first_monthly_fill_day'])
        self.assertEqual(first_week['covered_by'], 'monthly')

    def test_report_list_quarterly_fill_actions_are_only_on_first_missing_daily_row(self):
        quarterly_record = QPRRecord.objects.create(
            user=self.user,
            officeName='Office',
            officeCode='OFF',
            region='Region A',
            quarter='30 जून / Jun 30',
            year='2026-2027',
            frequency='quarterly',
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            status='Submitted',
            is_submitted=True,
        )
        QuarterlyFill.objects.create(
            user=self.user,
            quarter='30 जून / Jun 30',
            year='2026-2027',
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            s2_meetings=9,
        )

        request = self.factory.get('/qpr/reports/')
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        with patch('website.views.render', return_value=HttpResponse('ok')) as render_mock:
            response = report_list.__wrapped__(request)
            context = render_mock.call_args[0][2]

        self.assertEqual(response.status_code, 200)
        summary = json.loads(context['summary_json'])
        apr_1 = next(d for d in summary['daily'] if d['period_start'] == '2026-04-01')
        apr_2 = next(d for d in summary['daily'] if d['period_start'] == '2026-04-02')
        first_week = next(w for w in summary['weekly'] if w['period_start'] == '2026-04-01')
        april = next(m for m in summary['monthly'] if m['period_start'] == '2026-04-01')

        self.assertTrue(apr_1['filled_by_quarterly'])
        self.assertTrue(apr_1['is_first_quarterly_fill_day'])
        self.assertEqual(apr_1['quarterly_record_id'], quarterly_record.pk)
        self.assertTrue(apr_2['filled_by_quarterly'])
        self.assertFalse(apr_2['is_first_quarterly_fill_day'])
        self.assertEqual(first_week['covered_by'], 'quarterly')
        self.assertEqual(april['covered_by'], 'quarterly')

    def test_division_qpr_uses_subordinate_quarterly_snapshots_not_quarterly_fill_values(self):
        hod_role, _ = Role.objects.get_or_create(name='hod')
        user_role, _ = Role.objects.get_or_create(name='user')
        hod_user = CustomUser.objects.create_user(
            username='hod-division',
            email='hod-division@example.com',
            password='password123'
        )
        hod_user.roles.add(hod_role)
        hod_user.profile.roles.add(hod_role)
        hod_user.profile.name = 'Division HOD'
        hod_user.profile.hod_name = 'Division HOD'
        hod_user.profile.approval_status = 'approved'
        hod_user.profile.save()

        self.user.roles.add(user_role)
        self.user.profile.roles.add(user_role)
        self.user.profile.hod_name = 'Division HOD'
        self.user.profile.approval_status = 'approved'
        self.user.profile.save()

        QuarterlyFill.objects.create(
            user=self.user,
            quarter='30 जून / Jun 30',
            year='2026-2027',
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            s2_meetings=99,
        )
        QuarterlySnapshot.objects.create(
            user=self.user,
            quarter='30 जून / Jun 30',
            year='2026-2027',
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            s2_meetings=4,
        )

        request = self.factory.get('/qpr/reports/0/?division=1')
        request.user = hod_user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        with patch('website.views.render', return_value=HttpResponse('ok')) as render_mock:
            response = report_detail.__wrapped__(request, 0)
            context = render_mock.call_args[0][2]

        self.assertEqual(response.status_code, 200)
        payload = json.loads(context['initial_qpr_json'])
        self.assertEqual(payload['s2_meetings'], 4)

    def test_weekly_snapshot_approval_cannot_update_daily_record_directly(self):
        record = self._record('daily', date(2026, 4, 6), date(2026, 4, 6))
        EditRequest.objects.create(
            user=self.user,
            request_type='qpr',
            qpr_record_id=record.pk,
            requested_data={'edit_scope': 'weekly'},
            status='approved',
        )

        request = self.factory.post('/qpr/records/save/', {
            'id': str(record.pk),
            'status': 'Submitted',
            'officeName': 'Changed Office',
            'officeCode': 'CHG',
            'region': 'Region B',
            'quarter': record.quarter,
            'year': record.year,
            'frequency': 'daily',
            'details': '{"s2_meetings": "99"}',
        })
        request.user = self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))

        response = qpr_save_record.__wrapped__(request)

        record.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(record.officeName, 'Office')
        self.assertFalse(EditRequest.objects.filter(qpr_record_id=record.pk, status='temp use').exists())
