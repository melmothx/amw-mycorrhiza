# -*- coding: utf-8 -*-
from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader
import json
from amwmeta.xapian import search
import logging
from django.urls import reverse
from amwmeta.utils import paginator

logger = logging.getLogger(__name__)

# Create your views here.

def index(request):
    template = loader.get_template("search/index.html")
    query_params = request.GET
    context = search(query_params)
    logger.debug(context)
    baseurl = reverse('index')
    context['paginations'] = paginator(context['pager'], baseurl, query_params)
    return HttpResponse(template.render(context,request))
