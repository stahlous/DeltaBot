

# Top Ten View Changers ({{ month }})
    

| Rank | Username | Deltas |
| :------: | ------ | :------: |
{%- for leader in leaders %}
{%- if loop.index == 1 %}
| **1** | **/u/{{ leader[0] }}** | [**{{ leader[1] }}**](/r/stahlous/wiki/user/{{ leader[0] }} \"Delta history\") |
{%- else %}
| {{ loop.index }} | /u/{{ leader[0] }} | [{{ leader[1] }}](/r/stahlous/wiki/user/{{ leader[0] }} \"Delta history\") |
{%- endif %}
{%- endfor %}
