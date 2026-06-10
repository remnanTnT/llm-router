from django.core.management.base import BaseCommand
from django.utils import timezone
from router.services.cmdb import CMDBService
from router.repositories.ips import IPRepository
from router.repositories.user_ips import UserIPRepository
from router.config import APP_CONFIG


class Command(BaseCommand):
    help = "Refresh user_ips table from CMDB source. Supports dry-run to generate SQL."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Do not update DB, just print the SQL commands.")
        parser.add_argument("--ip", type=str, help="Specific IP to refresh.")

    def handle(self, *args, **options):
        if not APP_CONFIG.get("cmdb", {}).get("enabled", False):
            self.stdout.write(self.style.ERROR("CMDB is not enabled in config.yaml"))
            return

        dry_run = options.get("dry_run")
        ip_filter = options.get("ip")

        if ip_filter:
            ips = IPRepository.all_active()
            ips = [ip for ip in ips if ip.ip == ip_filter]
            if not ips:
                self.stdout.write(self.style.WARNING(f"IP {ip_filter} not found or inactive."))
                return
        else:
            ips = IPRepository.all_active()

        service = CMDBService()
        if not hasattr(service, "fetch_user_data"):
            self.stdout.write(self.style.ERROR("Error: CMDBService does not yet implement 'fetch_user_data(ip) -> dict'."))
            self.stdout.write("Please implement this method in 'router/services/cmdb.py' to enable this command.")
            return

        now = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        
        sql_commands = []

        for ip_row in ips:
            # We assume fetch_user_data returns the dictionary of values from CMDB
            user_data = service.fetch_user_data(ip_row.ip)
            if not user_data:
                self.stdout.write(f"Skipping {ip_row.ip}: no data from CMDB")
                continue

            if dry_run:
                sql = self._generate_upsert_sql(ip_row.id, user_data, now)
                sql_commands.append(sql)
            else:
                UserIPRepository.create_or_update(
                    ip_id=ip_row.id,
                    user_name=user_data.get("user_name", ""),
                    user_charge=user_data.get("user_charge", ""),
                    employee_no=user_data.get("employee_no", ""),
                    department_id=user_data.get("department_id"),
                )
                self.stdout.write(f"Successfully refreshed {ip_row.ip}")

        if dry_run and sql_commands:
            self.stdout.write("\n-- GENERATED SQL COMMANDS --")
            for cmd in sql_commands:
                self.stdout.write(cmd)
            
            self.stdout.write("\n" + "="*40)
            self.stdout.write("To run these commands manually against the database:")
            self.stdout.write("1. Save the SQL to a file (e.g., updates.sql)")
            self.stdout.write("2. Run: psql -h <db_host> -p <db_port> -U <user> -d <db_name> -f updates.sql")
            self.stdout.write("="*40)
        elif dry_run:
            self.stdout.write("No updates needed or no data found to generate SQL.")

    def _generate_upsert_sql(self, ip_id, user_data, now_str):
        user_name = user_data.get("user_name", "").replace("'", "''")
        user_charge = user_data.get("user_charge", "").replace("'", "''")
        employee_no = user_data.get("employee_no", "").replace("'", "''")
        dept_id = user_data.get("department_id")
        dept_val = str(dept_id) if dept_id is not None else "NULL"
        
        return (
            f"INSERT INTO user_ips (ip_id, user_name, user_charge, employee_no, department_id, is_valid, created_at, updated_at) "
            f"VALUES ({ip_id}, '{user_name}', '{user_charge}', '{employee_no}', {dept_val}, true, '{now_str}', '{now_str}') "
            f"ON CONFLICT (ip_id) DO UPDATE SET "
            f"user_name = EXCLUDED.user_name, "
            f"user_charge = EXCLUDED.user_charge, "
            f"employee_no = EXCLUDED.employee_no, "
            f"department_id = EXCLUDED.department_id, "
            f"updated_at = EXCLUDED.updated_at;\n"
        )
