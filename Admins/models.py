from django.db import models
from django.contrib.auth.models import User

class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateField()
    time = models.TimeField()
    venue = models.CharField(max_length=200)
    poster = models.ImageField(upload_to="event_posters/")
    price = models.FloatField()
    total_tickets = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Ticket(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    token_id = models.IntegerField()
    owner_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="owned_tickets")
    owner_wallet = models.CharField(max_length=200, default="")  
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"Ticket {self.token_id} for {self.event.title}"
