import datetime
import os
import pprint

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView
from django.views.decorators.http import require_POST
from django.urls import reverse, reverse_lazy
from pylti1p3.contrib.django import DjangoOIDCLogin, DjangoMessageLaunch, DjangoCacheDataStorage
from pylti1p3.contrib.django.lti1p3_tool_config import DjangoDbToolConf
from pylti1p3.contrib.django.lti1p3_tool_config.dynamic_registration import DjangoDynamicRegistration
from pylti1p3.deep_link_resource import DeepLinkResource
from pylti1p3.exception import LtiServiceException
from pylti1p3.grade import Grade
from pylti1p3.lineitem import LineItem
from pylti1p3.roles import TeacherRole, StudentRole

PAGE_TITLE = 'LTI 1.3 example'
PAGE_DESCRIPTION = 'A demonstration of pylti1p3'

class ExtendedDjangoMessageLaunch(DjangoMessageLaunch):

    def validate_nonce(self):
        """

        This subclass is not needed for production use.

        Probably it is bug on "https://lti-ri.imsglobal.org":
        site passes invalid "nonce" value during deep links launch.
        Because of this in case of iss == http://imsglobal.org just skip nonce validation.

        """
        iss = self.get_iss()
        deep_link_launch = self.is_deep_link_launch()
        if iss == "http://imsglobal.org" and deep_link_launch:
            return self
        return super().validate_nonce()


class LTIView:
    """
        A view mixin which adds a message_launch object to the view object.
        The message launch data is loaded from POST parameters, so this .

        For views which need access to the launch data after the launch/login flow, use CachedLTIView.
    """

    tool_conf = DjangoDbToolConf()
    launch_data_storage = DjangoCacheDataStorage()

    message_launch_cls = ExtendedDjangoMessageLaunch

    def dispatch(self, request, *args, **kwargs):
        self.message_launch = self.get_message_launch()
        return super().dispatch(request, *args, **kwargs)

    def get_message_launch(self):
        message_launch = self.message_launch_cls(self.request, self.tool_conf, launch_data_storage = self.launch_data_storage)
        return message_launch


class CachedLTIView(LTIView):
    """
        A view mixin which adds a message_launch object to the view object.
        The message launch data is loaded from cache storage.

        The ID of the launch must be provided either as a POST parameter or in the query part of the URL under the key defined by the launch_id_param property.
    """

    launch_id_param = 'launch_id'

    def get_launch_id(self):
        return self.request.POST.get(self.launch_id_param, self.kwargs.get(self.launch_id_param))

    def get_message_launch(self):
        launch_id = self.get_launch_id()

        message_launch = self.message_launch_cls.from_cache(launch_id, self.request, self.tool_conf, launch_data_storage = self.launch_data_storage)

        return message_launch

class LoginView(LTIView, View):
    """
        LTI login: verify the credentials, and redirect to the target link URI given in the launch parameters.
        The OIDCLogin object handles checking that cookies can be set.
    """
    http_method_names = ['post', 'get']

    def get_launch_url(self):
        """
            Get the intended launch URL during a login request.
        """

        target_link_uri = self.request.POST.get('target_link_uri', self.request.GET.get('target_link_uri'))
        if not target_link_uri:
            raise Exception('Missing "target_link_uri" param')
        return target_link_uri

    def dispatch(self, request, *args, **kwargs):
        oidc_login = DjangoOIDCLogin(request, self.tool_conf, launch_data_storage = self.launch_data_storage)
        target_link_uri = self.get_launch_url()
        return oidc_login\
            .enable_check_cookies()\
            .redirect(target_link_uri)

class LaunchView(LTIView, TemplateView):
    """
        Handle a launch activity.

        There are several kinds of launch; the kind of launch is given by the message_launch object.
    """
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data(**kwargs))

    def get_template_names(self):
        """
            Choose which template to render based on the launch type and the user's roles.
        """
        if self.message_launch.check_teacher_access() or self.message_launch.check_teaching_assistant_access():
            if self.message_launch.is_deep_link_launch():
                return ['deep_link.html']
            else:
                return ['teacher.html']
        elif self.message_launch.check_student_access():
            return ['student.html']
        else:
            raise Exception(f"You have an unknown role.")

    def get_special_word(self):
        """
            The deep-linking launch allows the teacher to choose a letter to associate with this link.

            In real use, the chosen object could be a particular quiz, or a chapter from a book.

            The chosen letter is passed as a custom parameter in the launch data.
        """
        message_launch_data = self.message_launch.get_launch_data()

        special_word = message_launch_data.get('https://purl.imsglobal.org/spec/lti/claim/custom', {})\
            .get('special_word', None)

        return special_word

    def get_context_data(self):
        message_launch_data = self.message_launch.get_launch_data()
        message_type = message_launch_data.get("https://purl.imsglobal.org/spec/lti/claim/message_type")

        return {
            'page_title': PAGE_TITLE,
            'launch_data': message_launch_data,
            'launch_id': self.message_launch.get_launch_id(),
            'curr_user_name': message_launch_data.get('name', ''),
            'curr_diff': self.get_special_word(),
            'special_word': self.get_special_word(),
            'message_type': message_type,
        }

class LaunchDataView(CachedLTIView, View):
    """
        Show all the LTI launch data.

        You wouldn't do this in a real LTI tool, but it helps to see real data when learning how the protocol works.
    """

    def get(self, request, *args, **kwargs):
        message_launch_data = self.message_launch.get_launch_data()

        return render(self.request, 'launch_data.html', {
            'launch_id': self.message_launch.get_launch_id(),
            'launch_data': message_launch_data,
            'custom_params': message_launch_data.get('https://purl.imsglobal.org/spec/lti/claim/custom', {}),
        })


class JWKSView(LTIView, View):
    """
        Return the tool's JSON Web Key Set.
    """
    def get(self, request, *args, **kwargs):
        return JsonResponse(self.tool_conf.get_jwks(), safe=False)

class CompleteDeepLinkView(CachedLTIView, View):
    """
        Change the configuration of the tool, completing a deep link launch.
    """
    http_method_names = ['post']

    def get_deep_link_resource(self):
        resource = DeepLinkResource()

        launch_url = self.request.build_absolute_uri(reverse('game-launch'))

        special_word = self.request.POST.get('special-word')

        return resource\
            .set_url(launch_url)\
            .set_custom_params({'special_word': special_word})\
            .set_title(f'Activity with the special word "{special_word}"')

    def post(self, request, *args, **kwargs):
        if not self.message_launch.is_deep_link_launch():
            return HttpResponseForbidden('Must be a deep link!')

        resource = self.get_deep_link_resource()

        html = self.message_launch.get_deep_link().output_response_form([resource])
        return HttpResponse(html)


class SetScoreView(CachedLTIView, View):
    """
        Report a score back to the platform's assignments and grades service.


        This needs the scope 
            'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem'
        if it will create a lineitem, or
            'https://purl.imsglobal.org/spec/lti-ags/scope/score'
        if a lineitem already exists and has been included in the launch data.
            
    """
    def get_launch_id(self):
        return self.kwargs['launch_id']

    def post(self, request, *args, **kwargs):
        resource_link_id = self.message_launch.get_launch_data() \
            .get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')

        if not self.message_launch.has_ags():
            return HttpResponseForbidden("This launch doesn't provide a grades service!")

        sub = self.message_launch.get_launch_data().get('sub')
        timestamp = datetime.datetime.utcnow().isoformat() + 'Z'
        score = int(self.request.POST.get('score'))
        activity_progress = self.request.POST.get('activity-progress')
        grading_progress = self.request.POST.get('grading-progress')

        ags = self.message_launch.get_ags()

        try:
            if ags.can_create_lineitem():
                print("Create lineitem")
                sc = Grade()
                sc.set_score_given(score)\
                    .set_score_maximum(100)\
                    .set_timestamp(timestamp)\
                    .set_activity_progress(activity_progress)\
                    .set_grading_progress(grading_progress)\
                    .set_user_id(sub)

                sc_line_item = LineItem()
                sc_line_item.set_tag('score')\
                    .set_score_maximum(100)\
                    .set_label('Score')
                if resource_link_id:
                    sc_line_item.set_resource_id(resource_link_id)

                result = ags.put_grade(sc, sc_line_item)
            else:
                print("No line item")
                sc = Grade()
                sc.set_score_given(score) \
                    .set_score_maximum(100) \
                    .set_timestamp(timestamp) \
                    .set_activity_progress(activity_progress) \
                    .set_grading_progress(grading_progress) \
                    .set_user_id(sub)
                result = ags.put_grade(sc)

            return JsonResponse({'success': True, 'result': result.get('body')})
        
        except LtiServiceException as e:
            return JsonResponse({'success': False, 'result': str(e)})

class ScoreboardView(CachedLTIView, TemplateView):
    """
        Look at the scoreboard - show roles and scores for every member of this launch's context.
    """
    template_name = 'scoreboard.html'

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)

        resource_link_id = self.message_launch.get_launch_data() \
            .get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')

        if not self.message_launch.has_nrps():
            return HttpResponseForbidden("Don't have names and roles!")

        if not self.message_launch.has_ags():
            return HttpResponseForbidden("Don't have grades!")

        ags = self.message_launch.get_ags()

        if ags.can_create_lineitem():
            score_line_item = LineItem()
            score_line_item.set_tag('score') \
                .set_score_maximum(100) \
                .set_label('Score')
            if resource_link_id:
                score_line_item.set_resource_id(resource_link_id)

            score_line_item = ags.find_or_create_lineitem(score_line_item)
            scores = ags.get_grades(score_line_item)
        else:
            scores = ags.get_grades()
            times = None

        members = self.message_launch.get_nrps().get_members()

        for m in members:
            data = {'https://purl.imsglobal.org/spec/lti/claim/roles': m['roles']}
            m['teacher'] = TeacherRole(data).check()
            m['student'] = StudentRole(data).check()

        ctx['members'] = members

        member_by_user = {m['user_id']: m for m in members}
        for s in scores:
            member_by_user[s['userId']]['score'] = s

        return ctx

class DynamicRegistration(DjangoDynamicRegistration):
    """
        Dynamic registration handler.
    """
    client_name = PAGE_TITLE
    description = PAGE_DESCRIPTION

    initiate_login_url = reverse_lazy('game-login')
    jwks_url = reverse_lazy('game-jwks')
    launch_url = reverse_lazy('game-launch')

    def get_claims(self):
        return ['iss', 'sub', 'name']

    def get_scopes(self):
        return [
            'https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly',
            'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',
            'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly',
            'https://purl.imsglobal.org/spec/lti-ags/scope/score',
        ]

    def get_messages(self):
        return [{
            'type': 'LtiDeepLinkingRequest',
            'target_link_uri': self.request.build_absolute_uri(reverse('game-launch')),
            'label': 'New tool link',
        }]

def register(request):
    """
        Dynamic registration view.
        Triggers the dynamic registration handler, which creates an LtiTool entry in the database.
        Returns a page which does a JavaScript postMessage call to the platform to tell it that registration is complete.
    """
    registration = DynamicRegistration(request)

    lti_tool = registration.register()

    return HttpResponse(registration.complete_html())
