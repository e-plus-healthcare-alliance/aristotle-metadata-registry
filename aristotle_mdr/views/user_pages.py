import datetime
from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.shortcuts import render, redirect

from aristotle_mdr import forms as MDRForms
from aristotle_mdr import models as MDR
from aristotle_mdr.views.utils import paginated_list, paginated_reversion_list

from reversion.models import Revision, Version

@login_required
def home(request):
    #recent = Revision.objects.filter(user=request.user)

    #recent = Version.objects.filter(revision__user=request.user).order_by('-revision__date_created')[0:10]
    recent = Revision.objects.filter(user=request.user).order_by('-date_created')[0:10]
    page = render(request,"aristotle_mdr/user/userHome.html",{"item":request.user,'recent':recent})
    return page

@login_required
def recent(request):
    items = Revision.objects.filter(user=request.user).order_by('-date_created')
    context = { }
    return paginated_reversion_list(request,items,"aristotle_mdr/user/recent.html",context)

@login_required
def inbox(request,folder=None):
    if folder is None:
        # By default show only unread
        folder='unread'
    folder=folder.lower()
    if folder == 'unread':
        notices = request.user.notifications.unread().all()
    elif folder == "all" :
        notices = request.user.notifications.all()
    page = render(request,"aristotle_mdr/user/userInbox.html",
        {"item":request.user,"notifications":notices,'folder':folder})
    return page

@login_required
def admin_tools(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    aristotle_apps = getattr(settings, 'ARISTOTLE_SETTINGS', {}).get('CONTENT_EXTENSIONS',[])
    aristotle_apps += ["aristotle_mdr"]

    from django.contrib.contenttypes.models import ContentType
    models = ContentType.objects.filter(app_label__in=aristotle_apps).all()
    model_stats = {}

    for m in models:
        if issubclass(m.model_class(),MDR._concept) and not m.model.startswith("_"):
            # Only output subclasses of 11179 concept
            app_models = model_stats.get(m.app_label,{'app':None,'models':[]})
            if app_models['app'] is None:
                app_models['app'] = getattr(apps.get_app_config(m.app_label),'verbose_name')
            app_models['models'].append(
                    (m.model_class(),
                     get_cached_object_count(m),
                     reverse("admin:%s_%s_changelist" % (m.app_label, m.model))
                    )
                )
            model_stats[m.app_label] = app_models

    page = render(request,"aristotle_mdr/user/userAdminTools.html",
            {"item":request.user,"models":model_stats})
    return page

@login_required
def admin_stats(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    aristotle_apps = getattr(settings, 'ARISTOTLE_SETTINGS', {}).get('CONTENT_EXTENSIONS',[])
    aristotle_apps += ["aristotle_mdr"]

    from django.contrib.contenttypes.models import ContentType
    models = ContentType.objects.filter(app_label__in=aristotle_apps).all()
    model_stats = {}

    # Get datetime objects for '7 days ago' and '30 days ago'
    t7 = datetime.date.today() - datetime.timedelta(days=7)
    t30 = datetime.date.today() - datetime.timedelta(days=30)
    mod_counts = [] # used to get the maximum count

    use_cache = True # We still cache but its much, much shorter
    for m in models:
        if issubclass(m.model_class(),MDR._concept) and not m.model.startswith("_"):
            # Only output subclasses of 11179 concept
            app_models = model_stats.get(m.app_label,{'app':None,'models':[]})
            if app_models['app'] is None:
                app_models['app'] = getattr(apps.get_app_config(m.app_label),'verbose_name')
            if use_cache:
                total   = get_cached_query_count(
                        qs=m.model_class().objects,
                        key=model_to_cache_key(m)+"__all_time",
                        ttl=60
                        )
                t7_val  = get_cached_query_count(
                        qs=m.model_class().objects.filter(created__gte=t7),
                        key=model_to_cache_key(m)+"__t7",
                        ttl=60
                        )
                t30_val = get_cached_query_count(
                        qs=m.model_class().objects.filter(created__gte=t30),
                        key=model_to_cache_key(m)+"__t30",
                        ttl=60
                        )
            else:
                total   = m.model_class().objects.count()
                t7_val  = m.model_class().objects.filter(created__gte=t7).count()
                t30_val = m.model_class().objects.filter(created__gte=t30).count()

            mod_counts.append(total)
            app_models['models'].append(
                    (m.model_class(),
                     {  'all_time': total,
                        't7':t7_val,
                        't30':t30_val
                     },
                     reverse("admin:%s_%s_changelist" % (m.app_label, m.model))
                    )
                )
            model_stats[m.app_label] = app_models

    page = render(request,"aristotle_mdr/user/userAdminStats.html",
            {"item":request.user,"model_stats":model_stats,'model_max':max(mod_counts)})
    return page

def get_cached_query_count(qs,key,ttl):
    count = cache.get(key, None)
    if not count:
        count = qs.count()
        cache.set(key, count, ttl)
    return count

def model_to_cache_key(model_type):
    return 'aristotle_adminpage_object_count_%s_%s'%(model_type.app_label, model_type.model)

def get_cached_object_count(model_type):
    CACHE_KEY = model_to_cache_key(model_type)
    query = model_type.model_class().objects
    return get_cached_query_count(query,CACHE_KEY, 60*60*12) # Cache for 12 hours


@login_required
def edit(request):
    if request.method == 'POST': # If the form has been submitted...
        form = MDRForms.UserSelfEditForm(request.POST) # A form bound to the POST data
        if form.is_valid():
            # process the data in form.cleaned_data as required
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.email = form.cleaned_data['email']
            request.user.save()
            return redirect(reverse('aristotle:userHome',))
    else:
        form = MDRForms.UserSelfEditForm({
            'first_name':request.user.first_name,
            'last_name':request.user.last_name,
            'email':request.user.email,
            })
    return render(request,"aristotle_mdr/user/userEdit.html",{"form":form,})

@login_required
def favourites(request):
    items = request.user.profile.favourites.select_subclasses()
    context = { 'help':request.GET.get("help",False),
                'favourite':request.GET.get("favourite",False),}
    return paginated_list(request,items,"aristotle_mdr/user/userFavourites.html",context)

@login_required
def registrar_tools(request):
    if not request.user.profile.is_registrar:
        raise PermissionDenied
    page = render(request,"aristotle_mdr/user/userRegistrarTools.html")
    return page

@login_required
def review_list(request):
    if not request.user.profile.is_registrar:
        raise PermissionDenied
    items = MDR._concept.objects.visible(request.user).filter(readyToReview=True,statuses=None).select_subclasses()
    return paginated_list(request,items,"aristotle_mdr/user/userReadyForReview.html",{'items':items})

@login_required
def workgroups(request):
    page = render(request,"aristotle_mdr/user/userWorkgroups.html")
    return page

@login_required
def workgroup_archives(request):
    page = render(request,"aristotle_mdr/user/userWorkgroupArchives.html")
    return page
