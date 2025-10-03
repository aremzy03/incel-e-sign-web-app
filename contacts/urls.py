from django.urls import path
from .views import ContactListView, ContactSearchView, ContactAddView, ContactInviteView, ContactDeleteView

app_name = 'contacts'

urlpatterns = [
    path('', ContactListView.as_view(), name='contacts_list'),
    path('search/', ContactSearchView.as_view(), name='contacts_search'),
    path('add/', ContactAddView.as_view(), name='contacts_add'),
    path('invite/', ContactInviteView.as_view(), name='contacts_invite'),
    path('<uuid:pk>/delete/', ContactDeleteView.as_view(), name='contacts_delete'),
]


