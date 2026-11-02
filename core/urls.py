"""Core views and URLs"""
from django.urls import path
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from core.models import User, DiningHall, MealService, CostRate
from core.serializers import (
    UserSerializer, UserCreateSerializer, DiningHallSerializer,
    MealServiceSerializer, CostRateSerializer
)


class LoginView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if not user:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data
        })


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def profile_view(request):
    return Response(UserSerializer(request.user).data)


@api_view(['POST'])
def logout_view(request):
    request.user.auth_token.delete()
    return Response({'message': 'Logged out successfully'})


class UserListView(generics.ListCreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class DiningHallListCreateView(generics.ListCreateAPIView):
    queryset = DiningHall.objects.filter(is_active=True)
    serializer_class = DiningHallSerializer


class DiningHallDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = DiningHall.objects.all()
    serializer_class = DiningHallSerializer


class MealServiceListCreateView(generics.ListCreateAPIView):
    queryset = MealService.objects.filter(is_active=True).select_related('dining_hall')
    serializer_class = MealServiceSerializer
    filterset_fields = ['dining_hall', 'meal_type', 'is_active']


class MealServiceDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = MealService.objects.all()
    serializer_class = MealServiceSerializer


class CostRateListCreateView(generics.ListCreateAPIView):
    queryset = CostRate.objects.all()
    serializer_class = CostRateSerializer


urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('profile/', profile_view, name='profile'),
    path('logout/', logout_view, name='logout'),
    path('users/', UserListView.as_view(), name='users'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('dining-halls/', DiningHallListCreateView.as_view(), name='dining-halls'),
    path('dining-halls/<int:pk>/', DiningHallDetailView.as_view(), name='dining-hall-detail'),
    path('meal-services/', MealServiceListCreateView.as_view(), name='meal-services'),
    path('meal-services/<int:pk>/', MealServiceDetailView.as_view(), name='meal-service-detail'),
    path('cost-rates/', CostRateListCreateView.as_view(), name='cost-rates'),
]
