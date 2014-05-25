{{ awardee }} has received {{ num_awards }} delta{% if num_awards > 1 %}s{% endif %} for the following comment{% if num_awards > 1 %}s{% endif %}:

{% for awarded_comment in awarded_comments %}
* [{{ awarded_comment.submission_title }}]({{ awarded_comment.submission_url }}) ({{ awarded_comment.awarding_comments|length }})
{% for awarding_comment in awarded_comment.awarding_comments %}
  {{ loop.index }}. [Awarded by /u/{{ awarding_comment.author}}]({{ awarding_comment.url }}) on {{ dt.fromtimestamp(awarding_comment.time).strftime('%d %b %Y %H:%M') }}
{% endfor %}


{% endfor %}