from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):

	role = models.CharField(
		max_length=50,
		choices = [
			("manager","MANAGER"),
			("user","USER")
		],
		default = "user"
	)


	def get_fullname(self):
		return f"{self.first_name} {self.last_name}"

	def __str__(self):
		return f"{self.first_name}"