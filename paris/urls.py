from django.urls import path

from paris import views

urlpatterns = [
    path('competitions/', views.CompetitionList.as_view()),
    path('matchs/', views.MatchList.as_view()),
    path('matchs/<int:pk>/', views.MatchDetail.as_view()),
    path('matchs/<int:pk>/resultat/', views.MatchResultat.as_view()),
    path('matchs/<int:pk>/propositions/', views.PropositionListCreate.as_view()),
    path('matchs/<int:pk>/propositions/<int:prop_id>/vote/', views.PropositionVote.as_view()),
    path('matchs/<int:pk>/options/<int:opt_id>/vote/', views.OptionVote.as_view()),
    path('matchs/<int:pk>/pronostic/', views.PronosticMatch.as_view()),
    path('classement/', views.ClassementPremium.as_view()),
    path('equipes/<int:pk>/logo/', views.EquipeLogo.as_view()),
    path('equipes/<int:pk>/infos/', views.EquipeInfos.as_view()),
    path('historique/', views.Verification.as_view()),
    path('historique/detail/', views.VerificationDetail.as_view()),
    path('verification/', views.Verification.as_view()),
    path('verification/detail/', views.VerificationDetail.as_view()),
    path('salon/', views.ChatListCreate.as_view()),
    path('info/', views.Info.as_view()),
    path('auth/register/', views.Register.as_view()),
    path('auth/login/', views.Login.as_view()),
    path('auth/logout/', views.Logout.as_view()),
]
