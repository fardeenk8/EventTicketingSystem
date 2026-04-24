from django.urls import path
from Users.views import *

urlpatterns = [
    path('userhome/', userhome, name='userhome'),
    path('wallet/', user_wallet, name='user_wallet'),
    path('events/', browse_events, name='browse_events'),
    path('events/<int:event_id>/', event_detail, name='event_detail'),
    path('events/<int:event_id>/pricing/', event_pricing, name='event_pricing'),
    path('save_wallet/', save_wallet, name='save_wallet'),
    path('buy/<int:event_id>/', buy_ticket, name='buy_ticket'),
    path("my_tickets/", my_tickets, name="my_tickets"),
    path('download_ticket/<int:ticket_id>/', download_ticket, name="download_ticket"),
    path('transactions/', transaction_history, name="transaction_history"),
    path("resale_ticket/", resale_ticket, name="resale_ticket"),
    path("marketplace/", marketplace, name="marketplace"),
    path("buy_resale/<int:resale_id>/", buy_resale_ticket, name="buy_resale_ticket"),
    path("refund_ticket/", refund_ticket, name="refund_ticket"),
    path("auctions/create/", create_auction, name="create_auction"),
    path("auctions/place-bid/", place_bid, name="place_bid"),
    path("auctions/", auction_list, name="auction_list"),
    path("auctions/<int:auction_id>/", auction_details, name="auction_details"),
    path("auctions/<int:auction_id>/end-now/", end_auction_now, name="end_auction_now"),

]