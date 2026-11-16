from django.contrib import admin

from .models import Letter, Posting, Search

admin.site.register(Search)
admin.site.register(Letter)

@admin.register(Posting)
class PostingAdmin(admin.ModelAdmin):
  list_display = ("title", "company", "size", "career", "deadline", "source")
  list_filter = ("source", "size", "career")
  search_fields = ("title", "company", "tech_tags")
