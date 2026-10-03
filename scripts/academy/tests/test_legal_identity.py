"""Reviewed-PDF identity only; these tests make no HTML-semantic equivalence claim."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import plugin_agreement as plugin
import legal_preflight as pre
from test_plugin_agreement import PluginFixture

class PdfContractTests(unittest.TestCase):
    def test_only_two_exact_official_reviewed_pdf_destinations(self):
        pins=plugin.pins()
        self.assertEqual([p['url'] for p in pins],['https://www.jetbrains.com/legal/docs/terms/jetbrains-academy/plugin/plugin.pdf','https://www.jetbrains.com/legal/docs/privacy/privacy/privacy.pdf'])
        self.assertEqual({p['format'] for p in pins},{'pdf'})
        self.assertEqual({p['version'] for p in pins},{'1.3','3.2'})
        self.assertEqual({p['scope'] for p in pins},{'BASE_ACADEMY_PLUGIN_USAGE','JETBRAINS_PRIVACY_NOTICE'})
    def test_titles_dates_and_full_pdf_hashes_are_reviewed_constants(self):
        plugin_pdf,privacy_pdf=plugin.pins()
        self.assertEqual(plugin_pdf['title'],'JETBRAINS ACADEMY PLUGIN USER AGREEMENT');self.assertIn('February 24, 2025',plugin_pdf['version_line'])
        self.assertEqual(privacy_pdf['title'],'JetBrains Privacy Notice');self.assertIn('12 June 2026',privacy_pdf['version_line'])
        self.assertEqual(plugin_pdf['sha256'],'6720d6f4e78263d8cf7dadaa09b27e18873937715f423d5bae8dab27afb75a42')
        self.assertEqual(privacy_pdf['sha256'],'d664ac2c6bdc0a9598cad4afca09d5ae9b7348d528205b28e8335cf9243ac84f')
    def test_pinned_plugin_link_identity_keeps_ai_separate(self):
        pinfile=Path(plugin.__file__).with_name('academy-legal.json');value=json.loads(pinfile.read_text());links=value['ui_links']
        self.assertEqual(links['plugin'],'https://www.jetbrains.com/legal/docs/terms/jetbrains-academy/plugin/')
        self.assertEqual(links['privacy'],'https://www.jetbrains.com/legal/docs/privacy/privacy/')
        self.assertEqual(links['ai_not_accepted'],'https://www.jetbrains.com/legal/docs/terms/jetbrains-ai-service/')
        self.assertEqual(hashlib.sha256(json.dumps(links,sort_keys=True,separators=(',',':')).encode()).hexdigest(),plugin.LEGAL_ID['pinned_ui_links_sha256'])
    def test_checker_and_preflight_explicitly_do_not_verify_html_semantics(self):
        self.assertEqual(plugin.LEGAL_ID['verification_scope'],'REVIEWED_OFFICIAL_PDF_BYTES_ONLY')
        self.assertEqual(plugin.LEGAL_ID['html_semantics'],'NOT_VERIFIED')
        self.assertEqual(pre.PASS,'PASS_APPROVED_PDF_AVAILABILITY_NOT_ACCEPTANCE')
        self.assertNotIn('legal_identity.py',pre.FILES)
        self.assertFalse(Path(plugin.__file__).with_name('legal_identity.py').exists())
    def response(self,raw,url):
        value=Mock();value.__enter__=Mock(return_value=value);value.__exit__=Mock(return_value=False);value.status=200;value.geturl.return_value=url;value.read.return_value=raw;return value
    def check(self,second=None):
        bodies=[b'%PDF-synthetic-plugin',b'%PDF-synthetic-privacy']
        items=[{'format':'pdf','url':p['url'],'bytes':len(b),'sha256':plugin.digest(b)} for p,b in zip(plugin.pins(),bodies)]
        responses=[self.response(b,items[i]['url']) for i,b in enumerate(bodies)]
        if second is not None:responses[1]=self.response(second,items[1]['url'])
        opener=Mock();opener.open.side_effect=responses
        with patch.object(plugin,'pins',return_value=items),patch.object(plugin.urllib.request,'build_opener',return_value=opener),patch.object(plugin.time,'monotonic',return_value=50):value=plugin.fetch_legal(100)
        self.assertEqual(opener.open.call_count,2)
        self.assertEqual([c.args[0].full_url for c in opener.open.call_args_list],[i['url'] for i in items]);return value
    def test_complete_two_pdf_check_succeeds_without_html_request(self):self.assertEqual(self.check(),plugin.LEGAL_ID)
    def test_changed_truncated_or_extra_pdf_bytes_fail_closed(self):
        for raw in (b'%PDF-synthetic-privacY',b'',b'%PDF-synthetic-privacy-extra'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.check(raw)
    def test_html_response_cannot_substitute_for_pdf(self):
        with self.assertRaises(ValueError):self.check(b'<html>same version</html>')
    def test_later_changed_pdf_never_reuses_earlier_success(self):
        self.check()
        with self.assertRaises(ValueError):self.check(b'%PDF-synthetic-CHANGED')

class FreshReviewTests(PluginFixture):
    def test_known_mismatch_new_terms_or_wrong_review_basis_prevent_action(self):
        for name,value in [('known_terms_mismatch',True),('known_terms_mismatch',0),('new_terms_observed',True),('new_terms_observed',None),('legal_basis','CURRENT_HTML_EQUIVALENCE')]:
            bad=copy.deepcopy(self.approval);bad['visual_review'][name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):plugin.validate_control(bad,self.request)
    def test_review_fields_cannot_be_omitted_or_replaced_by_pdf_reachability(self):
        for key in ('known_terms_mismatch','new_terms_observed','legal_basis'):
            bad=copy.deepcopy(self.approval);bad['visual_review'].pop(key)
            with self.assertRaises(ValueError):plugin.validate_control(bad,self.request)
        with self.assertRaises(ValueError):plugin.validate_control({**self.request,'visual_review':{'status':pre.PASS}},self.request)
    def test_request_and_receipt_cannot_claim_live_html_was_verified(self):
        bad=copy.deepcopy(self.approval);bad['legal_identity']['html_semantics']='VERIFIED'
        with self.assertRaises(ValueError):plugin.validate_control(bad,self.request)
        self.assertEqual(self.request['legal_identity']['html_semantics'],'NOT_VERIFIED')

if __name__=='__main__':unittest.main()
