from django.views.generic import ListView, CreateView
from django.views.generic import UpdateView, DeleteView, DetailView
from django.shortcuts import get_object_or_404, redirect
from django.http import Http404  
from django.contrib.auth.mixins import LoginRequiredMixin  
from django.contrib.auth.models import User  
from django.utils import timezone  
from django.core.exceptions import PermissionDenied  
from django.db.models import Count  
from django.urls import reverse_lazy, reverse  

# Импорт локальных модулей: формы и модели
from .forms import CommentForm, PostForm, UserProfileForm
from .models import Post, Category, Comment


class PostListView(ListView):
    """
    Представление для отображения списка опубликованных постов.
    Наследуется от стандартного ListView Django.
    """
    model = Post  # Модель, с которой работает представление
    paginate_by = 10  # Количество постов на странице
    template_name = 'blog/index.html'  # Путь к шаблону

    def get_queryset(self):
        """
        Переопределяем queryset для фильтрации данных.
        Возвращает только опубликованные посты с корректными датами.
        """
        queryset = Post.objects.filter(
            is_published=True,  # Только опубликованные посты
            pub_date__lte=timezone.now(),  # Дата публикации не позднее текущего времени
            category__is_published=True  # Категория должна быть опубликована
        ).select_related('author').prefetch_related(  # Оптимизация запросов к БД
            'category', 'location').order_by('-pub_date').annotate(  # Сортировка по дате публикации
                comment_count=Count('comments')  # Добавляем количество комментариев
        )
        return queryset


class PostCreateView(LoginRequiredMixin, CreateView):
    """
    Представление для создания нового поста.
    Требует аутентификации пользователя.
    """
    model = Post
    form_class = PostForm  # Используемая форма для создания поста
    template_name = 'blog/create.html'
    login_url = '/login/'  # URL для перенаправления неаутентифицированных пользователей

    def form_valid(self, form):
        """
        Вызывается при успешной валидации формы.
        Автоматически устанавливает автора поста как текущего пользователя.
        """
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        """
        Определяет URL для перенаправления после успешного создания.
        Перенаправляет в профиль автора поста.
        """
        username = self.object.author.username
        return reverse('blog:profile', args=[username])


class PostUpdateView(UpdateView):
    """
    Представление для редактирования существующего поста.
    Не использует LoginRequiredMixin напрямую, но проверяет права через test_func.
    """
    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'  # Использует тот же шаблон, что и создание

    def test_func(self):
        """
        Проверяет права пользователя на редактирование поста.
        Возвращает True только если пользователь является автором поста.
        """
        self.object = self.get_object()
        return (
            self.request.user.is_authenticated
            and self.object.author == self.request.user
        )

    def dispatch(self, request, *args, **kwargs):
        """
        Перехватывает запрос до вызова основного метода.
        Проверяет права пользователя и перенаправляет, если нет прав.
        """
        if not self.test_func():
            # Перенаправляем на страницу поста, если нет прав на редактирование
            return redirect(reverse(
                'blog:post_detail', kwargs={'post_id': self.kwargs['pk']}
            ))
        else:
            return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        """Перенаправляет на страницу отредактированного поста."""
        return reverse_lazy(
            'blog:post_detail', kwargs={'post_id': self.object.pk}
        )


class PostDeleteView(LoginRequiredMixin, DeleteView):
    """
    Представление для удаления поста.
    Доступно только для аутентифицированных пользователей.
    """
    model = Post
    template_name = 'blog/create.html'  # Шаблон для подтверждения удаления
    success_url = reverse_lazy('blog:index')  # Куда перенаправлять после удаления
    pk_url_kwarg = 'post_id'  # Имя параметра в URL для идентификатора поста

    def get_queryset(self):
        """
        Ограничивает queryset - пользователь может удалять только свои посты.
        """
        qs = super().get_queryset()
        return qs.filter(author=self.request.user)


class PostDetailView(DetailView):
    """
    Представление для детального просмотра поста.
    """
    model = Post
    template_name = 'blog/detail.html'

    def get_object(self, queryset=None):
        """
        Переопределяем получение объекта для дополнительных проверок.
        Показывает пост только если:
        1. Пользователь является автором, ИЛИ
        2. Пост опубликован, категория опубликована, и дата публикации корректна.
        """
        post_id = self.kwargs.get('post_id')
        post = get_object_or_404(Post, id=post_id)
        if (
            post.author == self.request.user
            or (post.is_published and post.category.is_published
                and post.pub_date <= timezone.now())
        ):
            return post
        raise Http404('Страница не найдена')  # Иначе возвращаем 404

    def get_context_data(self, **kwargs):
        """
        Добавляет в контекст форму для комментариев и список комментариев.
        """
        context = super().get_context_data(**kwargs)
        post = self.get_object()
        comments = post.comments.all().order_by('created_at')  # Комментарии по порядку создания
        context['form'] = CommentForm()  # Пустая форма для нового комментария
        context['comments'] = comments  # Список существующих комментариев
        return context


class ProfileView(ListView):
    """
    Представление для отображения профиля пользователя со всеми его постами.
    """
    model = Post
    template_name = 'blog/profile.html'
    paginate_by = 10

    def get_queryset(self):
        """
        Возвращает все посты указанного пользователя.
        """
        username = self.kwargs['username']
        profile = get_object_or_404(User, username=username)
        posts = Post.objects.filter(author=profile).select_related(
            'author').prefetch_related('comments', 'category', 'location')
        posts_annotated = posts.annotate(comment_count=Count('comments'))
        return posts_annotated.order_by('-pub_date')

    def get_context_data(self, **kwargs):
        """
        Добавляет объект профиля в контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        if 'profile' not in context:
            context['profile'] = get_object_or_404(
                User, username=self.kwargs['username'])
        return context


class CategoryPostsView(ListView):
    """
    Представление для отображения постов определенной категории.
    """
    model = Post
    paginate_by = 10
    template_name = 'blog/category.html'

    def get_queryset(self):
        """
        Возвращает посты указанной категории с проверкой её публикации.
        """
        self.category = get_object_or_404(
            Category, slug=self.kwargs['category_slug'], is_published=True
        )

        queryset = Post.objects.filter(
            is_published=True,
            pub_date__lte=timezone.now(),
            category=self.category
        ).select_related('author', 'category', 'location').order_by('-pub_date')

        queryset = queryset.annotate(comment_count=Count('comments'))
        queryset = queryset.filter(category__is_published=True)  # Дублирующая проверка

        return queryset

    def get_context_data(self, **kwargs):
        """
        Добавляет объект категории в контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context


class EditProfileView(LoginRequiredMixin, UpdateView):
    """
    Представление для редактирования профиля пользователя.
    """
    model = User
    form_class = UserProfileForm
    template_name = 'blog/user.html'

    def get_success_url(self):
        """Перенаправляет на профиль пользователя после редактирования."""
        return reverse_lazy(
            'blog:profile', kwargs={'username': self.object.username}
        )

    def get_object(self):
        """Возвращает текущего пользователя для редактирования."""
        return self.request.user


class AddCommentView(LoginRequiredMixin, CreateView):
    """
    Представление для добавления комментария к посту.
    """
    model = Comment
    form_class = CommentForm
    template_name = 'comments.html'  # Возможно опечатка: должен быть blog/comments.html

    def get_success_url(self):
        """Перенаправляет на страницу поста после добавления комментария."""
        post_id = self.kwargs.get('post_id')
        return reverse('blog:post_detail', kwargs={'post_id': post_id})

    def form_valid(self, form):
        """
        Автоматически связывает комментарий с постом и автором.
        """
        post_id = self.kwargs.get('post_id')
        post = get_object_or_404(Post, id=post_id)
        form.instance.post = post
        form.instance.author = self.request.user
        return super().form_valid(form)


class EditCommentView(LoginRequiredMixin, UpdateView):
    """
    Представление для редактирования комментария.
    """
    model = Comment
    form_class = CommentForm
    template_name = 'blog/comment.html'
    success_url = reverse_lazy('blog:index')

    def dispatch(self, request, *args, **kwargs):
        """
        Проверяет, является ли пользователь автором комментария.
        """
        self.object = self.get_object()
        if self.object.author != request.user:
            raise PermissionDenied(
                'Вы не авторизованы для редактирования этого комментария.'
            )
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        """Получает комментарий по ID из URL."""
        comment_id = self.kwargs.get('comment_id')
        return get_object_or_404(Comment, id=comment_id)

    def get_context_data(self, **kwargs):
        """Добавляет ID поста в контекст."""
        context = super().get_context_data(**kwargs)
        context['post_id'] = self.kwargs.get('post_id')
        return context


class DeleteCommentView(LoginRequiredMixin, DeleteView):
    """
    Представление для удаления комментария.
    """
    model = Comment
    template_name = 'blog/comment.html'
    pk_url_kwarg = 'comment_id'  # Имя параметра для ID комментария

    def dispatch(self, request, *args, **kwargs):
        """
        Проверяет права на удаление комментария.
        """
        self.object = self.get_object()
        if self.object.author != request.user:
            raise PermissionDenied(
                'Вы не авторизованы для удаления этого комментария.'
            )
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        """Перенаправляет на страницу поста после удаления комментария."""
        post_id = self.kwargs.get('post_id')
        return reverse_lazy('blog:post_detail', kwargs={'post_id': post_id})

    def post(self, request, *args, **kwargs):
        """
        Явно обрабатывает POST запрос для удаления.
        Нужно для корректной работы с подтверждением удаления.
        """
        return self.delete(request, *args, **kwargs)