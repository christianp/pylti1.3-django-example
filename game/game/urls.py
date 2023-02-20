from django.contrib import admin
from django.urls import re_path, path
from .views import LoginView, LaunchView, JWKSView, CompleteDeepLinkView, SetScoreView, ScoreboardView, LaunchDataView, register

urlpatterns = [
    path('admin/', admin.site.urls),
    path(r'login/', LoginView.as_view(), name='game-login'),
    path(r'register/', register, name='register'),
    path(r'launch/', LaunchView.as_view(), name='game-launch'),
    path(r'jwks/', JWKSView.as_view(), name='game-jwks'),
    path(r'complete-deep-link/', CompleteDeepLinkView.as_view(), name='game-complete-deep-link'),
    re_path(r'^api/score/(?P<launch_id>[\w-]+)/$', SetScoreView.as_view(),
         name='game-api-set-score'),
    re_path(r'^scoreboard/(?P<launch_id>[\w-]+)/$', ScoreboardView.as_view(), name='scoreboard'),
    re_path(r'^launch-data/(?P<launch_id>[\w-]+)/$', LaunchDataView.as_view(), name='launch_data'),
]
