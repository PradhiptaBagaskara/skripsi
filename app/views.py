# -*- encoding: utf-8 -*-
"""
License: MIT
Copyright (c) 2019 - present AppSeed.us
"""

from django.contrib.auth.decorators import login_required, permission_required
from django.core.files.storage import FileSystemStorage
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.template import loader
from django.http import HttpResponse, HttpResponseRedirect
from binfile.check import checks as chk
from app.forms import InputForm, DocumentForm
from app.models import Document, Similarity
from app.task import process_doc, finishing_dataset, check_similarity, extract_n_process
from django.contrib import messages


@login_required(login_url="/login/")
def pages(request):
    context = {}
    # All resource paths end in .html.
    # Pick out the html file name from the url. And load that template.
    try:

        load_template = request.path.split('/')[-1]
        template = loader.get_template('pages/' + load_template)
        return HttpResponse(template.render(context, request))

    except:

        template = loader.get_template('pages/error-404.html')
        return HttpResponse(template.render(context, request))


@login_required(login_url="/login/")
def index(request):
    return render(request, "index.html")


@login_required(login_url="/login/")
def check(request):
    form = InputForm(request.POST or None)
    msg = None
    data = None
    diff = None

    if request.method == "POST":
        if form.is_valid():
            origin = form.cleaned_data.get("origin")
            referer = form.cleaned_data.get("referer")
            gram_option = int(form.cleaned_data.get("gram_option"))
            winnow_option = int(form.cleaned_data.get("winnow_option"))
            debug = bool(form.cleaned_data.get("debug") == '1')
            plag = int(form.cleaned_data.get("plag_option"))
            diff = chk(origin, referer, gram_option, winnow_option, debug, plag)
            if diff is not None:
                data = diff
            else:
                msg = 'Error on Checking'
        else:
            msg = 'No input specified'

    messages.success(request, msg)
    context = {"form": form, "msg": msg, "data": data}
    template = loader.get_template('check.html')
    return HttpResponse(template.render(context, request))


@login_required(login_url="/login/")
@permission_required('app.view_document')
@permission_required('app.view_document')
def document_list(request):
    documents = Document.objects.filter(user=request.user, is_dataset=False).order_by('-modified', '-created')
    msg = ""

    context = {"documents": documents, "msg": msg}
    template = loader.get_template('document/index.html')
    return HttpResponse(template.render(context, request))


@login_required(login_url="/login/")
@permission_required('app.add_document')
def document_upload(request):
    form = DocumentForm(request.POST, request.FILES)
    msg = None

    if request.method == "POST":
        if form.is_valid():
            doc = form.save(commit=False)
            doc.original_filename = request.FILES['content'].name
            doc.user = request.user
            doc.save()
            process_doc(doc.id)
            msg = 'Document Uploaded'
            messages.success(request, msg)
            return redirect("document.index")
        else:
            msg = 'No input specified'

    context = {"form": form, "msg": msg}
    template = loader.get_template('document/upload.html')
    return HttpResponse(template.render(context, request))


@login_required(login_url="/login/")
@permission_required('app.view_document')
def document_show(request, id):
    document = get_object_or_404(Document, id=id)
    msg = ""
    if hasattr(document, 'similarity'):
        document.similarity_table = document.similarity.get_result(True)

    context = {"document": document, "msg": msg}
    template = loader.get_template('document/detail.html') if not document.is_dataset else loader.get_template('dataset/detail.html')
    return HttpResponse(template.render(context, request))


@login_required(login_url="/login/")
@permission_required('app.change_document')
@permission_required('app.change_dataset')
def document_edit(request, id):
    document = get_object_or_404(Document, id=id)
    form = DocumentForm(instance=document)
    msg = None

    if request.method == "POST":
        form = DocumentForm(request.POST, instance=document)
        if form.is_valid():
            form.save()
            msg = 'Updated'
            messages.success(request, msg)
            return redirect("dataset.index" if document.is_dataset else "document.index")
        else:
            msg = 'No input specified'

    context = {"document": document, "form": form, "msg": msg}
    template = loader.get_template('document/edit.html')
    return HttpResponse(template.render(context, request))


@login_required(login_url="/login/")
@permission_required('app.delete_document')
def document_delete(request, id):
    document = get_object_or_404(Document, id=id)
    msg = "Dataset Deleted!" if document.is_dataset else "Document Deleted!"
    document.delete()

    messages.warning(request, msg)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


@login_required(login_url="/login/")
@permission_required('app.change_document')
def document_finishing(request, id):
    doc = get_object_or_404(Document, id=id)
    if doc.is_dataset:
        finishing_dataset(doc.id)
    else:
        process_doc(doc.id)

    messages.success(request, "Start Finishing...")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


@login_required
@permission_required('app.view_document')
def document_fingerprint(request, id):
    file = get_object_or_404(Document, id=id)
    import json
    response = HttpResponse(json.dumps(file.get_fingerprint()))
    response.status_code = 200
    response['Access-Control-Allow-Origin'] = '*'
    response['Content-Type'] = 'text/json'
    return response


@login_required
@permission_required('app.view_document')
def document_html(request, id):
    file = get_object_or_404(Document, id=id)
    response = HttpResponse(file.get_html())
    response.status_code = 200
    response['Access-Control-Allow-Origin'] = '*'
    response['Content-Type'] = 'text/html'
    response['X-Frame-Options'] = 'ALLOW'
    return response


@login_required
@permission_required('app.view_document')
@permission_required('app.view_similarity')
def document_similarity(request, id):
    file = get_object_or_404(Document, id=id)
    if not hasattr(file, 'similarity'):
        HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    response = HttpResponse(file.similarity.get_result(True))
    response.status_code = 200
    response['Access-Control-Allow-Origin'] = '*'
    response['Content-Type'] = 'text/html'
    return response


@login_required(login_url="/login/")
@permission_required('app.change_document')
@permission_required('app.add_similarity')
def similarity_check(request, id):
    document = get_object_or_404(Document, id=id)
    if not document.is_dataset:
        check_similarity(document.id)

    messages.success(request, "Starting Similarity Checking...")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


@login_required(login_url="/login/")
@permission_required('app.view_document')
@permission_required('app.view_dataset')
def dataset_list(request):
    datasets = Document.objects.filter(is_dataset=True).order_by('-modified', '-created')
    msg = ""

    context = {"datasets": datasets, "msg": msg}
    template = loader.get_template('dataset/index.html')
    return HttpResponse(template.render(context, request))


@login_required(login_url="/login/")
@permission_required('app.add_document')
@permission_required('app.add_dataset')
def dataset_upload(request):
    form = DocumentForm(request.POST, request.FILES)
    msg = None

    if request.method == "POST":
        if form.is_valid():
            doc = form.save(commit=False)
            doc.original_filename = request.FILES['content'].name
            doc.user = request.user
            doc.is_dataset = True
            doc.save()
            finishing_dataset(doc.id)
            msg = 'Dataset Uploaded'
            messages.success(request, msg)
            return redirect('dataset.index')
        else:
            msg = 'No input specified'

    context = {"form": form, "msg": msg}
    template = loader.get_template('dataset/upload.html')
    return HttpResponse(template.render(context, request))


@login_required(login_url="/login/")
@permission_required('app.add_document')
@permission_required('app.add_dataset')
def dataset_upload_batch(request):
    msg = None
    if request.method == 'POST' and request.FILES['dataset_batch']:
        dataset_batch = request.FILES['dataset_batch']
        fs = FileSystemStorage()
        filename = fs.save(dataset_batch.name, dataset_batch)
        uploaded_file_url = fs.url(filename)
        context = {
            'uploaded_file_url': uploaded_file_url
        }
        msg = "Extracting and Processing Datasets..."
        messages.success(request, msg)
        extract_n_process(filename, request.user.username)

    context = {}
    template = loader.get_template('dataset/upload_batch.html')
    return HttpResponse(template.render(context, request))

