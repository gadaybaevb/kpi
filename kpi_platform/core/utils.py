from .models import AuditLog


def log_action(user, action, obj, changes=""):
    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=obj.__class__.__name__,
        object_id=obj.id,
        changes=changes
    )