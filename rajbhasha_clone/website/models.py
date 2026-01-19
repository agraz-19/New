
from django.db import models

class Employee(models.Model):
    empcode = models.IntegerField()
    ename = models.CharField('Name in English', max_length=255)
    hname = models.CharField('Name in Hindi', max_length=255)
    desig = models.CharField('Designation in English', max_length=100)
    gazet = models.TextField(blank=False)
    prabodh = models.TextField(blank=False)
    praveen = models.TextField(blank=False)
    pragya = models.TextField(blank=False)
    parangat = models.TextField(blank=False)
    typing = models.TextField(blank=False)
    hindiproficiency = models.TextField(blank=False)
    lastupdate = models.DateField('Last Updated on', auto_now=True)
    superannuationDate = models.DateField('Superannuation Date', null=True, blank=True)

    def __str__(self):
        return self.ename
