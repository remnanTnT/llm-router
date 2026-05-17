from django.db import models


class TimestampedSoftDeleteModel(models.Model):
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True


class IP(TimestampedSoftDeleteModel):
    ip = models.CharField(max_length=50, unique=True)
    concurrent_multiplier = models.FloatField(default=1.0)

    class Meta:
        managed = False
        db_table = "ips"


class Department(TimestampedSoftDeleteModel):
    dept1 = models.CharField(max_length=100, blank=True, default="")
    dept2 = models.CharField(max_length=100, blank=True, default="")
    dept3 = models.CharField(max_length=100, blank=True, default="")
    dept4 = models.CharField(max_length=100, blank=True, default="")
    is_allowed = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "departments"
        unique_together = (("dept1", "dept2", "dept3", "dept4"),)


class UserIP(TimestampedSoftDeleteModel):
    ip_id = models.IntegerField(unique=True, blank=True, null=True)
    user_name = models.CharField(max_length=100, blank=True, default="")
    user_charge = models.CharField(max_length=100, blank=True, default="")
    department_id = models.IntegerField(blank=True, null=True)
    employee_no = models.CharField(max_length=50, blank=True, default="")
    is_valid = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "user_ips"


class UserVisitCount(TimestampedSoftDeleteModel):
    employee_no = models.CharField(max_length=50)
    visit_count = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "user_visit_counts"


class Model(models.Model):
    model_name = models.CharField(max_length=100, unique=True)
    concurrent_limit = models.IntegerField(blank=True, null=True, default=3)
    max_tokens = models.IntegerField(default=20480)

    class Meta:
        managed = False
        db_table = "models"


class Server(TimestampedSoftDeleteModel):
    model_id = models.IntegerField(blank=True, null=True)
    base_url = models.CharField(max_length=500, unique=True)
    is_online = models.BooleanField(default=True)
    weight = models.IntegerField(default=1)
    health_path = models.CharField(max_length=200, blank=True, default="/healthy")
    last_checked_at = models.DateTimeField(blank=True, null=True)
    last_failure_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "servers"


class RequestRecord(TimestampedSoftDeleteModel):
    user_ip_id = models.IntegerField(default=1)
    ip_id = models.IntegerField(blank=True, null=True)
    send_time = models.DateTimeField()
    end_time = models.DateTimeField(blank=True, null=True)
    latency = models.BigIntegerField(blank=True, null=True)
    model_id = models.IntegerField()
    input_token_cnt = models.IntegerField(default=0)
    output_token_cnt = models.IntegerField(default=0)
    task_status = models.CharField(max_length=20, default="processing")
    status = models.CharField(max_length=50, blank=True, null=True)
    fail_reason = models.CharField(max_length=100, blank=True, null=True)
    is_stream = models.BooleanField(blank=True, null=True)
    user_agent = models.CharField(max_length=500, blank=True, null=True)
    target_pod_ip = models.CharField(max_length=500, blank=True, null=True)
    attempt_count = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "requests"


class Whitelist(models.Model):
    employee_no = models.CharField(max_length=50, blank=True, default="")
    user_name = models.CharField(max_length=100, blank=True, default="")
    is_allowed = models.IntegerField(blank=True, null=True)
    update_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "whitelist"
