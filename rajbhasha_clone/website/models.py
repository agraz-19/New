
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
    PROFICIENCY_STATUS = [
        ("Passed", "Passed"),
        ("Did not Appear", "Did not Appear"),
    ]
    prabodh = models.CharField(max_length=20, default="", blank=True)
    praveen = models.CharField(max_length=20, default="", blank=True)
    pragya = models.CharField(max_length=20, default="", blank=True)
    parangat = models.CharField(max_length=20, default="", blank=True)
    typing = models.TextField()
    hindiproficiency = models.TextField()

    status = models.CharField(max_length=10,
    choices=[
        ("draft", "Draft"),
        ("submitted", "Submitted"),
    ],
    default="draft")
    lastupdate = models.DateTimeField('Last Updated On',auto_now=True)
    super_annuation_date = models.DateField('Superannuation Date',null=True,blank=True)

    def __str__(self):
        return self.ename
