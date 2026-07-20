import pytest
from django.core.management import call_command
from io import StringIO
from router.config import APP_CONFIG
from router.repositories.ips import IPRepository

@pytest.mark.django_db
def test_refresh_user_info_dry_run(monkeypatch):
    # Enable CMDB in config for the test
    monkeypatch.setitem(APP_CONFIG, "cmdb", {"enabled": True, "dummy": True})
    
    # Mock fetch_user_data
    from router.services.cmdb import CMDBService
    def mock_fetch(self, ip):
        return {
            "user_name": f"user_{ip.replace('.', '_')}",
            "user_charge": "default_charge",
            "employee_no": f"E{ip.split('.')[-1].zfill(5)}",
            "department_id": 1,
        }
    monkeypatch.setattr(CMDBService, "fetch_user_data", mock_fetch, raising=False)
    
    # Create an IP to refresh
    IPRepository.get_or_create("127.0.0.1")
    
    out = StringIO()
    call_command("refresh_user_info", "--dry-run", stdout=out)
    
    output = out.getvalue()
    assert "-- GENERATED SQL COMMANDS --" in output
    assert "INSERT INTO user_ips" in output
    assert "ON CONFLICT (ip_id) WHERE ip_id > 0" in output
    assert "127_0_0_1" in output
    assert "To run these commands manually against the database:" in output
    assert "psql -h <db_host>" in output

@pytest.mark.django_db
def test_refresh_user_info_actual_update(monkeypatch):
    # Enable CMDB in config for the test
    monkeypatch.setitem(APP_CONFIG, "cmdb", {"enabled": True, "dummy": True})
    
    # Mock fetch_user_data
    from router.services.cmdb import CMDBService
    def mock_fetch(self, ip):
        return {
            "user_name": f"user_{ip.replace('.', '_')}",
            "user_charge": "default_charge",
            "employee_no": f"E{ip.split('.')[-1].zfill(5)}",
            "department_id": 1,
        }
    monkeypatch.setattr(CMDBService, "fetch_user_data", mock_fetch, raising=False)
    
    # Create an IP
    ip_row, _ = IPRepository.get_or_create("192.168.1.1")
    
    out = StringIO()
    call_command("refresh_user_info", stdout=out)
    
    from router.models import UserIP
    user_ip = UserIP.objects.get(ip_id=ip_row.id)
    assert user_ip.user_name == "user_192_168_1_1"
    assert "Successfully refreshed 192.168.1.1" in out.getvalue()
