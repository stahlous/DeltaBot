

# Top Ten View Changers ({{ month }})
    

| Rank | Username | Deltas |
| :------: | ------ | :------: |
{%- for leader in leaders %}
{%- if loop.index == 1 %}
| **1** | **/u/{{ leader['awardee'] }}** | [**{{ leader['num_awards'] }}**](/r/stahlous/wiki/user/{{ leader['awardee'] }} \"Delta history\") |
{%- else %}
| {{ loop.index }} | /u/{{ leader['awardee'] }} | [{{ leader['num_awards'] }}](/r/stahlous/wiki/user/{{ leader['awardee'] }} \"Delta history\") |
{%- endif %}
{%- endfor %}
