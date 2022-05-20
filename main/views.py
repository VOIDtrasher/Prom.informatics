import json
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework import viewsets
from .models import Project, Student
from django.core.mail import send_mail
from .serializers import ProjectSerializer
from .additional import container_run, pop_avialable_port, check_existing_containers, create_socket_files, \
    uvicorn_start, project_clone, lead_to_useful_view, add_container_connection, element_build, get_port_by_name
import redis
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.core import serializers


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_queryset(self):
        start = self.request.query_params.get('start')
        number = self.request.query_params.get('number')
        name_filter = self.request.query_params.get('name')
        department_filter = self.request.query_params.get('department')
        author_filter = self.request.query_params.get('author')
        year_filter = self.request.query_params.get('year')
        mark_filter = self.request.query_params.get('mark')
        status = self.request.query_params.get('status')
        tech_stack=self.request.query_params.get('tech_stack')
        projects_by_filter = Project.objects.all()
        if name_filter:
            projects_by_filter = projects_by_filter.filter(name=name_filter)
        if department_filter:
            projects_by_filter = projects_by_filter.filter(department=department_filter)
        if author_filter:
            projects_by_filter = projects_by_filter.filter(author=author_filter)
        if year_filter:
            projects_by_filter = projects_by_filter.filter(year=year_filter)
        if mark_filter:
            projects_by_filter = projects_by_filter.filter(mark = mark_filter)
        if status:
            projects_by_filter = projects_by_filter.filter(status= status)
        if tech_stack:
            projects_by_filter = projects_by_filter.filter(techStack=tech_stack)
        if start is None:
            start = 0
        if number is None:
            number = len(projects_by_filter)
        queryset = projects_by_filter[int(start):int(start) + int(number)]
        return queryset


class RecentProjectViewSet(viewsets.ModelViewSet):
    recent_projects_amount = 5
    queryset = Project.objects.all().filter(status='approved').order_by("-upload_date")[:recent_projects_amount]
    serializer_class = ProjectSerializer

def index_page(request):

    if request.method == 'POST':
        body = request.body.decode('utf-8')
        """
            Добавление проекта
        """
        if json.loads(body)["requestType"] == 'elementAdd':
            name = json.loads(body)["currentAddName"]
            author = json.loads(body)["currentAddAuthor"]
            description = json.loads(body)['currentAddDescription']
            #todo: make tech stack
            department = json.loads(body)['currentAddDepartment']
            mark = json.loads(body)['currentAddMark']
            year = json.loads(body)['currentAddYear']
            images = json.loads(body)['currentAddImages']
            path_link = json.loads(body)['currentAddPathLink']
            tech_stack = json.loads(body)['currentTechStack']
            item = Project(name = name, author = author, description = description, mark = mark, year = year,
                           department = department, images = images, icon=images[0] if images else '',
                           path_link=path_link, tech_stack=tech_stack)
            item.save()
            send_mail(
                'Новый проект выслан на модерацию.',
                f'Новый проект с именем { name }, автор { author } ожидает Вашей модерации.',
                'prominfnotification@yandex.ru',
                ['matgost@yandex.ru'],
                fail_silently=False,
            )
        """
            Запуск проекта
        """
        if json.loads(body)["requestType"] == 'elementRun':

            current_element_id = json.loads(body)["elementId"]
            current_element = Project.objects.all().filter(id=current_element_id)[0]
            print(current_element.docker_status)
            cont_inf={}
            if current_element.docker_status == 'approved':
                    if not check_existing_containers(lead_to_useful_view(current_element.path_link)):
                        ports_get_request = pop_avialable_port()
                        cont_inf['id'] = ports_get_request[-1]
                        if ports_get_request != 'No free ports':
                            container_run(container_name=lead_to_useful_view(current_element.path_link), image_name=current_element.docker_image_name,
                                          ports=ports_get_request,
                                          volumes={f'prominformatics_run_config_{ports_get_request[-1]}':{'bind': '/run/', 'mode': 'rw'},
                                                   'prominformatics_socket_files':{'bind':'/container_copy_files/', 'mode':'ro'}})

                            create_socket_files(lead_to_useful_view(current_element.path_link))
                            uvicorn_start(lead_to_useful_view(current_element.path_link))
                            add_container_connection(lead_to_useful_view(current_element.path_link), ports_get_request)
                            return JsonResponse({'cont': cont_inf, 'status': 'ok'})
                        else:
                            return JsonResponse({'status': 'All ports are busy'})
                    else:
                        cont_inf['id'] = get_port_by_name(lead_to_useful_view(current_element.path_link))[-1]
                        return JsonResponse({'cont': cont_inf, 'status': 'Container with this name already exists'})
            else:
                return JsonResponse({'status': "There's no way to start this project with docker"})
        """
            Изменение статуса проекта (модерация)
        """
        #todo: Выяснить почему на модерации нет картинки
        if json.loads(body)["requestType"] == 'elementChangeStatus':
            element = Project.objects.get(id=json.loads(body)["elementId"])
            element.status = json.loads(body)["elementNewStatus"]
            element.docker_status = json.loads(body)["elementNewDockerStatus"]
            element.save(update_fields=['status', 'docker_status'])
            if element.tech_stack == 'Django-project':
                project_clone(element, json.loads(body)["personalAccessToken"])
                if element.docker_status == 'approved':
                    element.docker_image_name = element_build(element)
                    element.save(update_fields=['docker_image_name'])
                    return JsonResponse({'responseStatus': 'Successful build'})
            else:
                return JsonResponse({'responseStatus': 'Not avialiable (not Django project)'})

            return JsonResponse({'responseStatus':'success'})
        """
            Аутентификация пользователя
        """
        if json.loads(body)["requestType"] == 'userAuth':
            username = json.loads(body)["username"]
            password = json.loads(body)["password"]
            user = authenticate(username=username, password=password)
            print(username)
            print(password)
            if user is not None:
                user = User.objects.get(username=username)
                print(user)
                login(request, user)
                return JsonResponse({'responseStatus': 'Successfully authenticated'})
            else:
                return JsonResponse({'responseStatus': 'Authentication failed (Incorrect input values)'})
        """
            Регистрация
        """
        if json.loads(body)["requestType"] == 'userRegistry':
            if User.objects.filter(username=json.loads(body)["username"]):
                return JsonResponse({'responseStatus':'User with similar name already exists'})
            if User.objects.filter(email=json.loads(body)["email"]):
                return JsonResponse({'responseStatus':'User with similar E-mail already exists'})
            reg_user = User.objects.create_user(username=json.loads(body)["username"],
                                                password=json.loads(body)["password"], email=json.loads(body)["email"])
            if json.loads(body)["firstname"]:
                reg_user.firstname = json.loads(body)["firstname"]
            if json.loads(body)["secondname"]:
                reg_user.firstname = json.loads(body)["secondname"]
            reg_user.save()
            return JsonResponse({'responseStatus': 'Successfully saved'})
        """
            Проверка статуса пользователя
        """
        if json.loads(body)["requestType"] == 'authCheck':

            response = {}
            if request.user.is_authenticated:
                response['authStatus'] = 1
                response['currentUser'] = serializers.serialize('json', [request.user, ])
                if Student.objects.get(user_id=request.user.id).personal_access_token != 'no active gitlab connections':
                    response['gitlabStatus'] = 1
                    print(Student.objects.get(user_id=request.user.id))
                    response['privateAccessToken'] = Student.objects.get(user_id=request.user.id).personal_access_token
                    return JsonResponse(response)
                else:
                    response['gitlabStatus'] = 0
                    return JsonResponse(response)
            else:
                response['authStatus'] = 0
        """
            Выход из учётной записи
        """
        if json.loads(body)["requestType"] == 'userUnAuth':
            logout(request)
            return JsonResponse({'responseStatus': 'Successfull unauth'})
        """
            Аутентификация через гитлаб
        """
        if json.loads(body)["requestType"] == "gitlabAuth":
            element = Student.objects.get(user_id=request.user.id)
            if element.personal_access_token == 'no active gitlab connections':
                element.personal_access_token = json.loads(body)["personalAccessToken"]
                element.save(update_fields=['personal_access_token'])
                return JsonResponse({'responseStatus' : 'Successfully gitlab authorize'})
            else:
                return JsonResponse({'responseStatus': 'Unsuccessfully gitlab authorize'})
    return render(request, 'index.html', {})


def send_filter_params(request):
    departments = [dep['department'] for dep in list(Project.objects.all().values('department').distinct())]
    years = [ye['year'] for ye in list(Project.objects.all().values('year').distinct())]
    authors = [aut['author'] for aut in list(Project.objects.all().values('author').distinct())]
    marks = [mar['mark'] for mar in list(Project.objects.all().values('mark').distinct())]
    projects_amount = len(Project.objects.all())
    return JsonResponse(
        {
            'departments': departments,
            'years': years,
            'authors': authors,
            'marks': marks,
            'db_len': projects_amount,
        }
    )
