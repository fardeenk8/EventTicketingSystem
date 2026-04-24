from django.urls import path
from Admins.views import *

urlpatterns = [
    path('adminhome/', adminhome, name='adminhome'),
    path('admin_update_userstatus/<int:user_id>/', admin_update_userstatus, name='admin_update_userstatus'),
    path('create_event/', create_event, name='create_event'),
    path('event_list/', event_list, name='event_list'),
    path('mint_tickets/<int:event_id>/', admin_mint_tickets, name='admin_mint_tickets'),
    path('event/<int:event_id>/tickets/', event_tickets, name='event_tickets'),
    path('event/<int:event_id>/edit/', edit_event, name='edit_event'),
    path('event/<int:event_id>/delete/', delete_event, name='delete_event'),
    path('qr_scanner/', admin_qr_scanner, name='admin_qr_scanner'),
    path('validate_ticket/', validate_ticket, name='validate_ticket'),
    path("event/<int:event_id>/ticket_holders/", ticket_holders, name="ticket_holders"),
    path("event/<int:event_id>/sales_report/", sales_report, name="sales_report"),
    path("event/<int:event_id>/download_report/", download_sales_report, name="download_sales_report"),
    path("dashboard/", admin_dashboard, name="admin_dashboard"),
    path("refunds/", refund_requests, name="refund_requests"),
    path("refunds/approve/<int:refund_id>/", approve_refund, name="approve_refund"),
    path("refunds/reject/<int:refund_id>/", reject_refund, name="reject_refund"),

]