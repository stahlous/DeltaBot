{% for awardee, awards in awardee_awards.items() %}
## {{ awardee }} ({{ awards|length}})

{% for award in awards %}
* [{{ award.submission_title }}]({{ award.submission_url }})

{% endfor %}
{% endfor %}