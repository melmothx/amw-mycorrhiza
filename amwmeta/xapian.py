import json
import sys
import xapian
from sickle import Sickle
from sickle.oaiexceptions import *
from urllib.parse import urlparse
from pathlib import Path
import logging
from amwmeta.utils import DataPage
from sickle.models import Record
import re

logger = logging.getLogger(__name__)

XAPIAN_DB = str(Path(__file__).resolve().parent.parent.joinpath('xapian', 'db'))

# slot, prefix, boolean
FIELD_MAPPING = {
        'title':    (1, 'S',  False),
        'creator':  (2, 'XA', True),
        'subject':  (3, 'XK', True),
        'date':     (4, 'XP', True),
        'language': (5, 'L',  True),
        'hostname': (6, 'H',  True),
}

def search(query_params):
    db = xapian.Database(XAPIAN_DB)
    querystring = query_params.get("query")

    # todo setup validation in the views.py
    page_size = int(query_params.get("page_size", 10))
    if page_size < 1:
        page_size = 10

    page_number = int(query_params.get("page_number", 1))
    if page_number < 1:
        page_number = 1

    queryparser = xapian.QueryParser()
    queryparser.set_stemmer(xapian.Stem("none"))
    queryparser.set_stemming_strategy(queryparser.STEM_NONE)

    for field in FIELD_MAPPING:
        if FIELD_MAPPING[field][2]:
            queryparser.add_boolean_prefix(field, FIELD_MAPPING[field][1])
        else:
            queryparser.add_prefix(field, FIELD_MAPPING[field][1])

    context = {}
    spies = {}
    if querystring:
        context['querystring'] = querystring
    query = xapian.Query.MatchAll
    queryparser.set_default_op(xapian.Query.OP_AND)
    if querystring:
        logger.info("Query is " + querystring)
        flags = queryparser.FLAG_PHRASE | queryparser.FLAG_BOOLEAN  | queryparser.FLAG_LOVEHATE | queryparser.FLAG_WILDCARD
        query = queryparser.parse_query(querystring, flags)

    filter_queries = []
    active_facets = {}
    for field in FIELD_MAPPING:
        # booleans only
        if FIELD_MAPPING[field][2]:
            filters_ors = []
            active_facets[field] = []
            for value in query_params.getlist('filter_' + field):
                filter_value = FIELD_MAPPING[field][1] + value.lower();
                logger.info("Filter value is " + filter_value)
                if filter_value:
                    filters_ors.append(xapian.Query(filter_value))
                    active_facets[field].append(value)
            if len(filters_ors):
                filter_queries.append(xapian.Query(xapian.Query.OP_OR, filters_ors))

    logger.info(filter_queries)
    if len(filter_queries):
        query = xapian.Query(xapian.Query.OP_FILTER, query,
                             xapian.Query(xapian.Query.OP_AND, filter_queries))

    enquire = xapian.Enquire(db)
    enquire.set_query(query)
    matches = []
    facets = []
    for field in FIELD_MAPPING:
        # boolean only
        if FIELD_MAPPING[field][2]:
            # use the slot
            spy = xapian.ValueCountMatchSpy(FIELD_MAPPING[field][0])
            enquire.add_matchspy(spy)
            spies[field] = spy

    start = (page_number - 1) * page_size
    mset = enquire.get_mset(start, page_size, db.get_doccount())
    pager = DataPage(total_entries=mset.get_matches_estimated(),
                     entries_per_page=page_size,
                     current_page=page_number)
    logger.info(pager)

    for match in mset:
        fields = json.loads(match.document.get_data().decode('utf8'))
        rec = {}
        for field in fields:
            values = fields.get(field)
            if values:
                if field == "identifier":
                    urls = [ i for i in values if re.match(r'^https?://', i) ]
                    if len(urls):
                        rec['url'] = urls[0]
                        rec['identifiers'] = values
                elif field == "oai_pmh_identifier":
                    rec[field] = values
                else:
                    rec[field] = ' | '.join(values)

        logger.info(rec)
        matches.append(rec)

    for spy_name in spies:
        spy = spies[spy_name]
        facet_values = {}
        for facet in spy.values():
            # logger.info(facet.term)
            for facet_value in json.loads(facet.term.decode('utf-8')):

                facet_active = False
                if facet_value in active_facets[spy_name]:
                    facet_active = True

                if facet_value in facet_values:
                    facet_values[facet_value]['count'] += facet.termfreq
                else:
                    facet_values[facet_value] = {
                        "term": facet_value,
                        "count": facet.termfreq,
                        "active": facet_active,
                    }

        if len(facet_values):
            facets.append({
                "name": spy_name,
                "values": sorted(list(facet_values.values()), key=lambda el: (0 - el['count'], el['term'])),
            })

    context['matches'] = matches
    context['facets'] = facets
    context['filters'] = active_facets
    context['pager'] = pager
    context['querystring'] = querystring
    return context

class MarcXMLRecord(Record):
    def get_metadata(self):
        ns = { None: 'http://www.loc.gov/MARC21/slim' }
        specs = [
            # for now consider 720a the authors, including contributors
            # ('contributor', '720',  'a'),
            ('coverage', '500',  ('a')),
            ('creator', '100',  ('a')),
            ('creator', '720',  ('a')),
            ('date', '260',  ('c')),
            ('date', '363', ('i')), # normalized date
            ('date', '264', ('c')),
            ('description', '300', ('a', 'b', 'c', 'e')),
            ('description', '500', ('a')),
            ('description', '520',  ('a')),
            ('format', '856',  ('q')),
            ('identifier', '024',  ('a')),
            ('identifier', '856', ('u')),
            ('language', '546',  ('a')),
            ('language', '041', ('a')),
            ('publisher', '260',  ('b')),
            ('publisher', '264',  ('b')),
            ('publisher', '264', ('a', 'c')), # this is actually the place + date
            ('relation', '787',  ('n')),
            ('rights', '540',  ('a')),
            ('source', '786',  ('n')),
            ('subject', '653',  ('a')),
            ('title', '245',  ('a', 'b')),
            ('title', '246',  ('a')),
            ('type', '655',  ('a')),
            ('type', '336',  ('a')),
        ]
        out = {}
        for node in self.xml.findall('.//' + self._oai_namespace + 'metadata'):
            for spec in specs:
                target, tag, codes = spec
                if not target in out:
                    out[target] = []
                for el in node.findall('.//datafield[@tag="{0}"]'.format(tag), namespaces=ns):
                    values = []
                    for code in codes:
                        values.extend([ sf.text for sf in el.findall('.//subfield[@code="{0}"]'.format(code),
                                                                     namespaces=ns) ])
                    if len(values):
                        out[target].extend([' '.join(values)])
            break
        return out

def iso_lang_code(code):
    if not code:
        return None

    if len(code) == 2:
        return code.lower()

    if len(code) == 3:
        mapping = {
            'abk': 'ab',
            'aar': 'aa',
            'afr': 'af',
            'aka': 'ak',
            'sqi': 'sq',
            'amh': 'am',
            'ara': 'ar',
            'arg': 'an',
            'hye': 'hy',
            'asm': 'as',
            'ava': 'av',
            'ave': 'ae',
            'aym': 'ay',
            'aze': 'az',
            'bam': 'bm',
            'bak': 'ba',
            'eus': 'eu',
            'bel': 'be',
            'ben': 'bn',
            'bis': 'bi',
            'bos': 'bs',
            'bre': 'br',
            'bul': 'bg',
            'mya': 'my',
            'cat': 'ca',
            'cha': 'ch',
            'che': 'ce',
            'nya': 'ny',
            'zho': 'zh',
            'chu': 'cu',
            'chv': 'cv',
            'cor': 'kw',
            'cos': 'co',
            'cre': 'cr',
            'hrv': 'hr',
            'ces': 'cs',
            'dan': 'da',
            'div': 'dv',
            'nld': 'nl',
            'dzo': 'dz',
            'eng': 'en',
            'epo': 'eo',
            'est': 'et',
            'ewe': 'ee',
            'fao': 'fo',
            'fij': 'fj',
            'fin': 'fi',
            'fra': 'fr',
            'fry': 'fy',
            'ful': 'ff',
            'gla': 'gd',
            'glg': 'gl',
            'lug': 'lg',
            'kat': 'ka',
            'deu': 'de',
            'ell': 'el',
            'kal': 'kl',
            'grn': 'gn',
            'guj': 'gu',
            'hat': 'ht',
            'hau': 'ha',
            'heb': 'he',
            'her': 'hz',
            'hin': 'hi',
            'hmo': 'ho',
            'hun': 'hu',
            'isl': 'is',
            'ido': 'io',
            'ibo': 'ig',
            'ind': 'id',
            'ina': 'ia',
            'ile': 'ie',
            'iku': 'iu',
            'ipk': 'ik',
            'gle': 'ga',
            'ita': 'it',
            'jpn': 'ja',
            'jav': 'jv',
            'kan': 'kn',
            'kau': 'kr',
            'kas': 'ks',
            'kaz': 'kk',
            'khm': 'km',
            'kik': 'ki',
            'kin': 'rw',
            'kir': 'ky',
            'kom': 'kv',
            'kon': 'kg',
            'kor': 'ko',
            'kua': 'kj',
            'kur': 'ku',
            'lao': 'lo',
            'lat': 'la',
            'lav': 'lv',
            'lim': 'li',
            'lin': 'ln',
            'lit': 'lt',
            'lub': 'lu',
            'ltz': 'lb',
            'mkd': 'mk',
            'mlg': 'mg',
            'msa': 'ms',
            'mal': 'ml',
            'mlt': 'mt',
            'glv': 'gv',
            'mri': 'mi',
            'mar': 'mr',
            'mah': 'mh',
            'mon': 'mn',
            'nau': 'na',
            'nav': 'nv',
            'nde': 'nd',
            'nbl': 'nr',
            'ndo': 'ng',
            'nep': 'ne',
            'nor': 'no',
            'nob': 'nb',
            'nno': 'nn',
            'iii': 'ii',
            'oci': 'oc',
            'oji': 'oj',
            'ori': 'or',
            'orm': 'om',
            'oss': 'os',
            'pli': 'pi',
            'pus': 'ps',
            'fas': 'fa',
            'pol': 'pl',
            'por': 'pt',
            'pan': 'pa',
            'que': 'qu',
            'ron': 'ro',
            'roh': 'rm',
            'run': 'rn',
            'rus': 'ru',
            'sme': 'se',
            'smo': 'sm',
            'sag': 'sg',
            'san': 'sa',
            'srd': 'sc',
            'srp': 'sr',
            'sna': 'sn',
            'snd': 'sd',
            'sin': 'si',
            'slk': 'sk',
            'slv': 'sl',
            'som': 'so',
            'sot': 'st',
            'spa': 'es',
            'sun': 'su',
            'swa': 'sw',
            'ssw': 'ss',
            'swe': 'sv',
            'tgl': 'tl',
            'tah': 'ty',
            'tgk': 'tg',
            'tam': 'ta',
            'tat': 'tt',
            'tel': 'te',
            'tha': 'th',
            'bod': 'bo',
            'tir': 'ti',
            'ton': 'to',
            'tso': 'ts',
            'tsn': 'tn',
            'tur': 'tr',
            'tuk': 'tk',
            'twi': 'tw',
            'uig': 'ug',
            'ukr': 'uk',
            'urd': 'ur',
            'uzb': 'uz',
            'ven': 've',
            'vie': 'vi',
            'vol': 'vo',
            'wln': 'wa',
            'cym': 'cy',
            'wol': 'wo',
            'xho': 'xh',
            'yid': 'yi',
            'yor': 'yo',
            'zha': 'za',
            'zul': 'zu',
        }
        return mapping.get(code.lower(), code.lower())


def harvest(**opts):
    url = opts.pop('url')
    hostname = urlparse(url).hostname
    if opts['metadataPrefix'] == 'marc21':
        sickle = Sickle(url, class_mapping={
            "ListRecords": MarcXMLRecord,
            "GetRecord": MarcXMLRecord,
        })
    else:
        sickle = Sickle(url)

    try:
        records = sickle.ListRecords(**opts)
    except NoRecordsMatch:
        return
    except Exception as e:
        print(e)
        return

    db = xapian.WritableDatabase(XAPIAN_DB, xapian.DB_CREATE_OR_OPEN)
    termgenerator = xapian.TermGenerator()
    termgenerator.set_stemmer(xapian.Stem("none"))

    logs = []
    tried = []
    try:
        for rec in records:
            rec.get_metadata()
            tried.append(rec)
    except Exception as e:
        print(e)

    for rec in tried:
        # print(rec)
        record = rec.get_metadata()
        is_deleted = rec.deleted
        # this is the link, we need the record header and store that
        identifier = rec.header.identifier
        doc = xapian.Document()
        termgenerator.set_document(doc)
        record['hostname'] = [ hostname ]

        for field in FIELD_MAPPING:
            values = record.get(field)
            slot, prefix, is_boolean = FIELD_MAPPING[field]
            if values:
                value_list = []
                for v in values:
                    # if it's a boolean, add it so
                    if field == 'language':
                        v = iso_lang_code(v)
                        if v is None:
                            continue

                    if is_boolean:
                        doc.add_boolean_term(prefix + v.lower())
                    # but index it anyway
                    termgenerator.index_text(v, 1, prefix)
                    value_list.append(v)

                doc.add_value(slot, json.dumps(value_list))

        # general search
        termgenerator.increase_termpos()
        for field in ['title', 'creator', 'subject', 'description']:
            values = record.get(field)
            if values:
                for v in values:
                    termgenerator.index_text(v)

        record['oai_pmh_identifier'] = identifier
        doc.set_data(json.dumps(record))
        idterm = u"Q" + identifier
        doc.add_boolean_term(idterm)
        if is_deleted:
            logs.append("Removing document " + idterm)
            db.delete_document(idterm)
        else:
            logs.append("Indexing " + idterm)
            db.replace_document(idterm, doc)
    return logs
