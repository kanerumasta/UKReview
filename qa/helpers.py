from collections import defaultdict
import random
from .models import UserSamplingPriority
from django.db.models import F

from django.contrib.auth import get_user_model
User = get_user_model()


ANSI_TABLE = [
    {"range": (1, 8),       "Reduced": (4, 5.46), "Normal": (4, 1.49), "Tightened": (5, 1.34)},
    {"range": (9, 15),      "Reduced": (4, 5.46), "Normal": (4, 1.49), "Tightened": (5, 1.34)},
    {"range": (16, 25),     "Reduced": (4, 5.46), "Normal": (4, 1.49), "Tightened": (7, 2.13)},

    {"range": (26, 50),     "Reduced": (4, 5.46), "Normal": (5, 3.33), "Tightened": (10, 2.14)},
    {"range": (51, 90),     "Reduced": (4, 5.46), "Normal": (7, 3.54), "Tightened": (15, 2.09)},
    {"range": (91, 150),    "Reduced": (4, 5.46), "Normal": (10, 3.27), "Tightened": (20, 2.03)},

    {"range": (151, 280),   "Reduced": (4, 5.46), "Normal": (15, 3.06), "Tightened": (25, 2.00)},
    {"range": (281, 400),   "Reduced": (5, 5.82), "Normal": (20, 2.93), "Tightened": (35, 1.87)},
    {"range": (401, 500),   "Reduced": (5, 5.82), "Normal": (25, 2.86), "Tightened": (35, 1.87)},

    {"range": (501, 1200),  "Reduced": (7, 5.34), "Normal": (35, 2.66), "Tightened": (50, 1.73)},
    {"range": (1201, 3200), "Reduced": (10, 4.72), "Normal": (50, 2.47), "Tightened": (75, 1.59)},
    {"range": (3201, 100000),"Reduced": (15, 4.32), "Normal": (75, 2.27), "Tightened": (100, 1.52)},
]


def get_sampling_values(lot_size: int, sampling_type: str):
    if lot_size <= 1:
        return {
            "sample_size": lot_size,          
            "acceptance_limit": 0,   
            "type": sampling_type,
            "lot_size": lot_size
        }
    for row in ANSI_TABLE:
        low, high = row["range"]

        if low <= lot_size <= high:
            n, M = row[sampling_type]   
            return {
                "sample_size": n,
                "acceptance_limit": M,
                "type": sampling_type,
                "lot_size": lot_size
            }

    raise ValueError(f"No sampling range found for lot size {lot_size}")


def stratified_sampling(jobs_for_sampling, sample_size):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Group jobs by user
    jobs_by_user = defaultdict(list)
    for job in jobs_for_sampling:
        jobs_by_user[job.user_id].append(job)

    num_users = len(jobs_by_user)
    if num_users == 0:
        return []

    # Get the users sorted by qa_count ASC (lowest first)
    sorted_users = sorted(
        jobs_by_user.keys(),
        key=lambda user_id: User.objects.get(id=user_id).qa_count
    )

    base_quota = sample_size // num_users
    remainder = sample_size % num_users

    sampled_jobs = []

    # Prioritized round-robin based on sorted users
    for user_id in sorted_users:
        user_jobs = jobs_by_user[user_id]
        quota = base_quota

        if remainder > 0:
            quota += 1
            remainder -= 1

        if len(user_jobs) <= quota:
            selected_jobs = user_jobs
        else:
            selected_jobs = random.sample(user_jobs, quota)

        sampled_jobs.extend(selected_jobs)

    # update qa count once per user
    update_users_qa_count(sampled_jobs)

    return sampled_jobs

def update_users_qa_count(sampled_jobs):
    user_ids = set(job.user_id for job in sampled_jobs)

    for user_id in user_ids:
        User.objects.filter(id=user_id).update(qa_count=F('qa_count') + 1)
