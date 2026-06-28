from core.models import CronJobLog


def log_cron_run(*, job_name: str, detail: str = "", success: bool = True) -> CronJobLog:
    return CronJobLog.objects.create(job_name=job_name, detail=detail, success=success)
