from django.urls import path

from accounts import manage, views

urlpatterns = [
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("onboarding/", views.OnboardingView.as_view(), name="onboarding"),
    path("profile/delete/", views.DeleteAccountView.as_view(), name="account_delete"),
    path("manage/questions/", manage.QuestionListView.as_view(), name="manage_questions"),
    path("manage/questions/new/", manage.QuestionCreateView.as_view(), name="manage_question_new"),
    path(
        "manage/questions/<int:pk>/edit/",
        manage.QuestionUpdateView.as_view(),
        name="manage_question_edit",
    ),
    path(
        "manage/questions/<int:pk>/move/<slug:direction>/",
        manage.QuestionMoveView.as_view(),
        name="manage_question_move",
    ),
    path(
        "manage/questions/<int:pk>/archive/",
        manage.QuestionArchiveView.as_view(archive=True),
        name="manage_question_archive",
    ),
    path(
        "manage/questions/<int:pk>/restore/",
        manage.QuestionArchiveView.as_view(archive=False),
        name="manage_question_restore",
    ),
]
