from django.urls import path
from . import views

urlpatterns = [
    path('api/message/', views.chatbot_message_api, name='chatbot_message_api'),
]
