from django.urls import path

from notifications import manage

urlpatterns = [
    path("manage/emails/", manage.EmailLogView.as_view(), name="manage_emails"),
    path("manage/emails/<int:pk>/", manage.EmailDetailView.as_view(), name="manage_email"),
    path("manage/messages/", manage.MessageListView.as_view(), name="manage_messages"),
    path("manage/messages/new/", manage.MessageComposeView.as_view(), name="manage_message_new"),
    path("manage/messages/<int:pk>/", manage.MessageDetailView.as_view(), name="manage_message"),
]
