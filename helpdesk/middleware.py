from django.shortcuts import redirect
import requests

REDIRECET_URL = 'https://pfm.nivoapp.com/'

class TokenAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.path.startswith(('/admin/','/login/')) or request.user.is_authenticated:
            response = self.get_response(request)
            return response
        
        # get x-token and user_id from params
        x_token = request.GET.get('x_token', None)
        user_id = request.GET.get('user_id', None)

        # check if link is shorter or not
        sl = request.GET.get('sl', None)

        if sl is not None:
            from helpdesk.models import ShorterLink
            from django.core.exceptions import ObjectDoesNotExist

            try:
                link = ShorterLink.objects.get(short_link=sl)
            except ObjectDoesNotExist:
                return redirect(REDIRECET_URL)
            
            x_token = link.long_link_json['x_token']
            user_id = link.long_link_json['user_id']
        
           
        # check if x-token exist
        if x_token is None:
            return redirect(REDIRECET_URL)
            # return JsonResponse({'error': True, 'message': 'x_token is not exists'}, status=404)

        # check if user_id exist
        if user_id is None:
            return redirect(REDIRECET_URL)
            # return JsonResponse({'error': True, 'message': 'user_id is not exists'}, status=404)

        headers = {
            'content-type': 'application/json',
            'x-token': x_token
        }
        # get user info from nivo
        res = requests.get('https://pfm.nivoapp.com/api/v1/users/user-info', headers=headers)

        # return error if res is not ok
        if res.status_code != 200:
            return redirect(REDIRECET_URL)
            # return JsonResponse({'error': True, 'message': 'Incorrect token credentials'}, status=401)

        data = res.json()

        # check if user_id mach the res userid
        if user_id != data['userId']:
            return redirect(REDIRECET_URL)
            # return JsonResponse({'error': True, 'message': 'Incorrect user_id'}, status=401)
        
        try:
            phone = data['user']['phoneNumber']
            # return JsonResponse({'phone': phone}, status=200)
        except Exception as e:
            print(e.__str__)
            return redirect(REDIRECET_URL)
            # return JsonResponse({'error': True, 'message': 'phone number not exist in nivo'}, status=400)

        # check if user loged in or log in the user
        from django.contrib.auth import get_user_model, login
        from helpdesk.models import UserToken

        User = get_user_model()
        
        if not request.user.is_authenticated:
            # values
            username = phone
            email = f'{phone}@nivo.com'
            password = 'helpDesk-' + email
            
            # get or create the user
            u = User.objects.get_or_create(email=email, username=username)[0]
            u.set_password(password)
            u.save()

            # get or create usertoken
            UserToken.objects.get_or_create(user=u, x_token=x_token, uid=user_id)

            # login the user
            login(request, u)
        
        if not request.user.is_authenticated:
            return redirect(REDIRECET_URL)
            # return JsonResponse({'error': True, 'message': 'can not log in'}, status=400)

        response = self.get_response(request)
        return response