"""
django-helpdesk - A Django powered ticket tracker for small enterprise.

(c) Copyright 2008 Jutda. All Rights Reserved. See LICENSE for details.

views/public.py - All public facing views, eg non-staff (no authentication
                  required) views.
"""
from datetime import datetime
import json
import logging
from importlib import import_module
from re import template

from django.core.exceptions import (
    ObjectDoesNotExist, PermissionDenied, ImproperlyConfigured,
)
from django.urls import reverse
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils.http import urlquote
from django.utils.translation import ugettext as _
from django.conf import settings
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import TemplateView
from django.views.generic.edit import FormView
from django.contrib.auth import authenticate, login

from helpdesk import settings as helpdesk_settings
from helpdesk.decorators import protect_view, is_helpdesk_staff
from helpdesk.serializers import TicketListSerializer
import helpdesk.views.staff as staff
import helpdesk.views.abstract_views as abstract_views
from helpdesk.lib import text_is_spam
from helpdesk.models import KBItem, Ticket, Queue, UserSettings, ShorterLink
from helpdesk.user import huser_from_request

logger = logging.getLogger(__name__)


def create_ticket(request, *args, **kwargs):
    if is_helpdesk_staff(request.user):
        return staff.CreateTicketView.as_view()(request, *args, **kwargs)
    else:
        return CreateTicketView.as_view()(request, *args, **kwargs)


class BaseCreateTicketView(abstract_views.AbstractCreateTicketMixin, FormView):

    def get_form_class(self):
        try:
            the_module, the_form_class = helpdesk_settings.HELPDESK_PUBLIC_TICKET_FORM_CLASS.rsplit(".", 1)
            the_module = import_module(the_module)
            the_form_class = getattr(the_module, the_form_class)
        except Exception as e:
            raise ImproperlyConfigured(
                f"Invalid custom form class {helpdesk_settings.HELPDESK_PUBLIC_TICKET_FORM_CLASS}"
            ) from e
        return the_form_class

    def dispatch(self, *args, **kwargs):
        request = self.request
        if not request.user.is_authenticated and helpdesk_settings.HELPDESK_REDIRECT_TO_LOGIN_BY_DEFAULT:
            return HttpResponseRedirect(reverse('login'))

        if is_helpdesk_staff(request.user) or \
                (request.user.is_authenticated and
                 helpdesk_settings.HELPDESK_ALLOW_NON_STAFF_TICKET_UPDATE):
            try:
                if request.user.usersettings_helpdesk.login_view_ticketlist:
                    return HttpResponseRedirect(reverse('helpdesk:list'))
                else:
                    return HttpResponseRedirect(reverse('helpdesk:dashboard'))
            except UserSettings.DoesNotExist:
                return HttpResponseRedirect(reverse('helpdesk:dashboard'))
        return super().dispatch(*args, **kwargs)

    def get_initial(self):
        initial_data = super().get_initial()

        # add pre-defined data for public ticket
        if hasattr(settings, 'HELPDESK_PUBLIC_TICKET_QUEUE'):
            # get the requested queue; return an error if queue not found
            try:
                initial_data['queue'] = Queue.objects.get(
                    slug=settings.HELPDESK_PUBLIC_TICKET_QUEUE,
                    allow_public_submission=True
                ).id
            except Queue.DoesNotExist as e:
                logger.fatal(
                    "Public queue '%s' is configured as default but can't be found",
                    settings.HELPDESK_PUBLIC_TICKET_QUEUE
                )
                raise ImproperlyConfigured("Wrong public queue configuration") from e
        if hasattr(settings, 'HELPDESK_PUBLIC_TICKET_PRIORITY'):
            initial_data['priority'] = settings.HELPDESK_PUBLIC_TICKET_PRIORITY
        if hasattr(settings, 'HELPDESK_PUBLIC_TICKET_DUE_DATE'):
            initial_data['due_date'] = settings.HELPDESK_PUBLIC_TICKET_DUE_DATE
        return initial_data

    def get_form_kwargs(self, *args, **kwargs):
        kwargs = super().get_form_kwargs(*args, **kwargs)
        if '_hide_fields_' in self.request.GET:
            kwargs['hidden_fields'] = self.request.GET.get('_hide_fields_', '').split(',')
        kwargs['readonly_fields'] = self.request.GET.get('_readonly_fields_', '').split(',')
        return kwargs

    def form_valid(self, form):
        request = self.request

        if not form.is_valid():
            print(form.errors)
        if text_is_spam(form.cleaned_data['body'], request):
            # This submission is spam. Let's not save it.
            return render(request, template_name='helpdesk/public_spam.html')
        else:
            ticket = form.save(user=self.request.user if self.request.user.is_authenticated else None)
            try:
                # * added by sia
                # return JsonResponse({'error': True, 'result': tk})
                # template_url = 'helpdesk/public_ticket_list.html'

                # tk = list_of_tickets(submitter_email=self.request.user.email)

                # return render(request, template_url, {
                #     'result': tk, 'submit': True
                # })
                return email_ticket_list(self.request)
                # return HttpResponseRedirect('%s?ticket=%s&email=%s&key=%s' % (
                #     reverse('helpdesk:public_view'),
                #     ticket.ticket_for_url,
                #     urlquote(ticket.submitter_email),
                #     ticket.secret_key)
                # )
            except ValueError:
                # if someone enters a non-int string for the ticket
                return HttpResponseRedirect(reverse('helpdesk:home'))


class CreateTicketIframeView(BaseCreateTicketView):
    template_name = 'helpdesk/public_create_ticket_iframe.html'

    @csrf_exempt
    @xframe_options_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def form_valid(self, form):
        if super().form_valid(form).status_code == 302:
            return HttpResponseRedirect(reverse('helpdesk:success_iframe'))


class SuccessIframeView(TemplateView):
    template_name = 'helpdesk/success_iframe.html'

    @xframe_options_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class CreateTicketView(BaseCreateTicketView):
    template_name = 'helpdesk/public_create_ticket.html'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Add the CSS error class to the form in order to better see them in the page
        form.error_css_class = 'text-danger'
        return form


class Homepage(CreateTicketView):
    template_name = 'helpdesk/public_homepage.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['kb_categories'] = huser_from_request(self.request).get_allowed_kb_categories()
        return context


def search_for_ticket(request, error_message=None):
    if hasattr(settings, 'HELPDESK_VIEW_A_TICKET_PUBLIC') and settings.HELPDESK_VIEW_A_TICKET_PUBLIC:
        email = request.GET.get('email', None)
        return render(request, 'helpdesk/public_view_form.html', {
            'ticket': False,
            'email': email,
            'error_message': error_message,
            'helpdesk_settings': helpdesk_settings,
        })
    else:
        raise PermissionDenied("Public viewing of tickets without a secret key is forbidden.")


@protect_view
def view_ticket(request):

    # * added by sia >>>>
    
    sl = request.GET.get('sl', None)
    
    # if this boolean is true its means ther is no short link and
    # we should get params from request
    default_operation = True
    
    if sl is not None:
        try:
            link = ShorterLink.objects.get(short_link=sl)
            default_operation = False
        except ObjectDoesNotExist:
            default_operation = True
                
    if default_operation:
        ticket_req = request.GET.get('ticket', None)
        email = request.GET.get('email', None)
        key = request.GET.get('key', '')
    else:
        # default opt is false its means that we
        # should get link params from short link
        ticket_req = link.long_link_json.get('ticket', None)
        email = link.long_link_json.get('email', None)
        key = link.long_link_json.get('key', '')

    # * added by sia <<<<

    if not (ticket_req and email):
        if ticket_req is None and email is None:
            return search_for_ticket(request)
        else:
            return search_for_ticket(request, _('Missing ticket ID or e-mail address. Please try again.'))

    queue, ticket_id = Ticket.queue_and_id_from_query(ticket_req)
    try:
        if hasattr(settings, 'HELPDESK_VIEW_A_TICKET_PUBLIC') and settings.HELPDESK_VIEW_A_TICKET_PUBLIC:
            ticket = Ticket.objects.get(id=ticket_id, submitter_email__iexact=email)
        else:
            ticket = Ticket.objects.get(id=ticket_id, submitter_email__iexact=email, secret_key__iexact=key)
    except (ObjectDoesNotExist, ValueError):
        return search_for_ticket(request, _('Invalid ticket ID or e-mail address. Please try again.'))

    if is_helpdesk_staff(request.user):
        redirect_url = reverse('helpdesk:view', args=[ticket_id])
        if 'close' in request.GET:
            redirect_url += '?close'
        return HttpResponseRedirect(redirect_url)

    if 'close' in request.GET and ticket.status == Ticket.RESOLVED_STATUS:
        from helpdesk.views.staff import update_ticket
        # Trick the update_ticket() view into thinking it's being called with
        # a valid POST.
        request.POST = {
            'new_status': Ticket.CLOSED_STATUS,
            'public': 1,
            'title': ticket.title,
            'comment': _('Submitter accepted resolution and closed ticket'),
        }
        if ticket.assigned_to:
            request.POST['owner'] = ticket.assigned_to.id
        request.GET = {}

        return update_ticket(request, ticket_id, public=True)

    # redirect user back to this ticket if possible.
    redirect_url = ''
    if helpdesk_settings.HELPDESK_NAVIGATION_ENABLED:
        redirect_url = reverse('helpdesk:view', args=[ticket_id])

    return render(request, 'helpdesk/public_view_ticket.html', {
        'key': key,
        'mail': email,
        'ticket': ticket,
        'helpdesk_settings': helpdesk_settings,
        'next': redirect_url,
    })


def change_language(request):
    return_to = ''
    if 'return_to' in request.GET:
        return_to = request.GET['return_to']

    return render(request, 'helpdesk/public_change_language.html', {'next': return_to})


def list_of_tickets(submitter_email):
    tickets = Ticket.objects.filter(submitter_email=submitter_email)

    from helpdesk.serializers import TicketSerializer
    tk=[]
    
    for ticket in tickets:
        tk.append({
            'ticket': TicketListSerializer(ticket).data,
            'queue': ticket.queue.title
        })
    return tk

# * added by sia
def email_ticket_list(request):
    """send list of users tickets"""

    template_url = 'helpdesk/public_ticket_list.html'

    email = request.user.email
    if not email:
        return JsonResponse({'error': True, 'message': 'email is none'})
    
    tk = list_of_tickets(submitter_email=email)

    print(tk)
    # return JsonResponse({'error': True, 'result': tk})
    return render(request, template_url, {
        'result': tk, 'submit': False
    })

# * added by sia
def test_data(request):
    try:
        q = Queue(
            slug='a',
            title='a',
            allow_public_submission=True
        )
        q.save()

        t = Ticket(
            title = 'aa',
            description='aa',
            queue=q,
            created=datetime.now(),
            submitter_email='09120535348@gmail.com',
        )
        t.save()
        
        return JsonResponse({'message': 'successful'}, status=200)
    except Exception as e:
        print(e.__str__)
        return JsonResponse({'message': 'failed'}, status=400)
