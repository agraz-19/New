from django.contrib import admin
from .models import (
    QPRRecord, Section1FilesData, Section2MeetingsData, 
    Section3OfficialLanguagesData, Section4HindiLettersData,
    Section5EnglishRepliedHindiData, Section6IssuedLettersData,
    Section7NotingsData, Section8WorkshopsData,
    Section9ImplementationCommitteeData, Section10HindiAdvisoryData,
    Section11SpecificAchievementsData, UserProfile, ManagerRequest
)


class Section1FilesDataInline(admin.TabularInline):
    model = Section1FilesData


class Section2MeetingsDataInline(admin.TabularInline):
    model = Section2MeetingsData


class Section3OfficialLanguagesDataInline(admin.TabularInline):
    model = Section3OfficialLanguagesData


class Section4HindiLettersDataInline(admin.TabularInline):
    model = Section4HindiLettersData


class Section5EnglishRepliedHindiDataInline(admin.TabularInline):
    model = Section5EnglishRepliedHindiData


class Section6IssuedLettersDataInline(admin.TabularInline):
    model = Section6IssuedLettersData


class Section7NotingsDataInline(admin.TabularInline):
    model = Section7NotingsData


class Section8WorkshopsDataInline(admin.TabularInline):
    model = Section8WorkshopsData


class Section9ImplementationCommitteeDataInline(admin.TabularInline):
    model = Section9ImplementationCommitteeData


class Section10HindiAdvisoryDataInline(admin.TabularInline):
    model = Section10HindiAdvisoryData


class Section11SpecificAchievementsDataInline(admin.TabularInline):
    model = Section11SpecificAchievementsData


@admin.register(QPRRecord)
class QPRRecordAdmin(admin.ModelAdmin):
    list_display = ['officeName', 'officeCode', 'region', 'quarter', 'status', 'created_at']
    list_filter = ['status', 'region', 'quarter', 'created_at']
    search_fields = ['officeName', 'officeCode', 'email', 'phone']
    readonly_fields = ['created_at', 'updated_at']
    
    inlines = [
        Section1FilesDataInline,
        Section2MeetingsDataInline,
        Section3OfficialLanguagesDataInline,
        Section4HindiLettersDataInline,
        Section5EnglishRepliedHindiDataInline,
        Section6IssuedLettersDataInline,
        Section7NotingsDataInline,
        Section8WorkshopsDataInline,
        Section9ImplementationCommitteeDataInline,
        Section10HindiAdvisoryDataInline,
        Section11SpecificAchievementsDataInline,
    ]
    
    fieldsets = (
        ('Header Information', {
            'fields': ('officeName', 'officeCode', 'phone', 'email', 'region', 'quarter', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# Register individual section models
admin.site.register(Section1FilesData)
admin.site.register(Section2MeetingsData)
admin.site.register(Section3OfficialLanguagesData)
admin.site.register(Section4HindiLettersData)
admin.site.register(Section5EnglishRepliedHindiData)
admin.site.register(Section6IssuedLettersData)
admin.site.register(Section7NotingsData)
admin.site.register(Section8WorkshopsData)
admin.site.register(Section9ImplementationCommitteeData)
admin.site.register(Section10HindiAdvisoryData)
admin.site.register(Section11SpecificAchievementsData)
admin.site.register(UserProfile)
admin.site.register(ManagerRequest)
