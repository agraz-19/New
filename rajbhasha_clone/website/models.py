from django.db import models

class Employee(models.Model):
    empcode = models.IntegerField(unique=True)
    ename = models.CharField(max_length=255)
    hname = models.CharField(max_length=255)

    designation = models.CharField(max_length=100)

    GAZET_CHOICES = [
        ("Gazetted", "Gazetted"),
        ("Non-Gazetted", "Non-Gazetted"),
    ]
    gazet = models.CharField(max_length=50, choices=GAZET_CHOICES)

    EXAM_STATUS = [
        ("Passed", "Passed"),
        ("Failed", "Failed"),
        ("Did not Appear", "Did not Appear"),
    ]
    prabodh = models.CharField(max_length=20, choices=EXAM_STATUS, blank=True)
    praveen = models.CharField(max_length=20, choices=EXAM_STATUS, blank=True)
    pragya = models.CharField(max_length=20, choices=EXAM_STATUS, blank=True)
    parangat = models.CharField(max_length=20, choices=EXAM_STATUS, blank=True)

    TYPING_CHOICES = [
        ("Hindi", "Hindi"),
        ("English", "English"),
        ("Both", "Both"),
    ]
    typing = models.CharField(max_length=30, choices=TYPING_CHOICES)

    HINDI_PROFICIENCY_CHOICES = [
        ("Good", "Good"),
        ("Average", "Average"),
        ("Basic", "Basic"),
    ]
    hindiproficiency = models.CharField(
        max_length=30, choices=HINDI_PROFICIENCY_CHOICES
    )

    status = models.CharField(
        max_length=10,
        choices=[("draft", "Draft"), ("submitted", "Submitted")],
        default="draft",
    )

    lastupdate = models.DateTimeField("Last Updated On", auto_now=True)
    super_annuation_date = models.DateField(
        "Superannuation Date", null=True, blank=True
    )

    def __str__(self):
        return f"{self.empcode} - {self.ename}"
