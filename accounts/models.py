from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):


	def get_fullname(self):
		return f"{self.first_name} {self.last_name}"

	def __str__(self):
		return f"{self.first_name}"