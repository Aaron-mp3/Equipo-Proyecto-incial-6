from django.shortcuts import render

def pantalla_inicio(request):
    return render(request, 'gestion/login.html')

def menu_principal(request):
    return render(request, 'gestion/menu_principal.html')

def registro(request):
    return render(request, 'gestion/registro.html')

def dashboard(request):
    return render(request, 'gestion/dashboard.html')
