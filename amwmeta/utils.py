# port of https://metacpan.org/pod/Data::Page
from dataclasses import dataclass
from urllib.parse import urlencode

@dataclass
class DataPage:
    """Class to manage pages"""
    total_entries: int = 0
    entries_per_page: int = 10
    current_page: int = 1

    def first_page(self):
        return 1

    def last_page(self):
        pages = self.total_entries / self.entries_per_page
        if pages == int(pages):
            last_page = int(pages)
        else:
            last_page = 1 + int(pages)
        if last_page < 1:
            last_page = 1
        return last_page

    def first(self):
        if self.total_entries == 0:
            return 0
        else:
            return int(((self.current_page - 1) * self.entries_per_page) + 1)

    def last(self):
        if self.current_page == self.last_page():
            return int(self.total_entries)
        else:
            return int(self.current_page * self.entries_per_page)

    def previous_page(self):
        if self.current_page > 1:
            return self.current_page - 1
        else:
            return None

    def next_page(self):
        if self.current_page < self.last_page():
            return self.current_page + 1
        else:
            return None


def paginator(pager, base_url, params):
    out = []
    common = []
    for param in params:
        if param != "page_number":
            for value in params.getlist(param):
                common.append((param, value))

    # nothing to show
    if pager.last_page() == 1:
        return None

    if pager.previous_page():
        out.append({
            "label": "Previous",
            "current": False,
            "url": get_paged_url(base_url, common, pager.previous_page()),
            "class": "page-link page-link-previous"
        })

    for num in range(pager.first_page(), pager.last_page() + 1):
        struct = {
            "label": num,
            "current": pager.current_page == num,
            "url": get_paged_url(base_url, common, num),
            "class": "page-link page-link-" + str(num)
        }
        out.append(struct)

    if pager.next_page():
        out.append({
            "label": "Next",
            "current": False,
            "url": get_paged_url(base_url, common, pager.next_page()),
            "class": "page-link page-link-next"
        })

    return out

def get_paged_url(base_url, common, num):
    query = common.copy()
    query.append(("page_number", num))
    return base_url + '?' + urlencode(query)
