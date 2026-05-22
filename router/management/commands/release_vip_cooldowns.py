from django.core.management.base import BaseCommand

from router.config import APP_CONFIG
from router.repositories.servers import ServerRepository


class Command(BaseCommand):
    help = "Demote VIP servers whose vip_cooldown timer has expired."

    def add_arguments(self, parser):
        parser.add_argument("--cooldown", type=int, help="Override vip.cooldown_seconds (seconds).")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        cooldown = options.get("cooldown")
        if cooldown is None:
            cooldown = int(APP_CONFIG.get("vip", {}).get("cooldown_seconds", 300))

        if options.get("dry_run"):
            self.stdout.write(f"Dry run: would demote VIP servers with vip_cooldown older than {cooldown}s")
            return

        demoted = ServerRepository.demote_expired_cooldowns(cooldown)
        self.stdout.write(self.style.SUCCESS(f"Demoted {demoted} VIP servers"))
