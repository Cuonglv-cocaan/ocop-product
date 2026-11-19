"""Central stylesheet composition. Inject APP_STYLES once per app run."""
from src.chat_styles import CHAT_CSS

COLOR_TOKENS = """:root {
    --ocop-text-primary:#183d2b;
    --ocop-text-product:#183d2b;
    --ocop-text-muted:#53675b;
    --ocop-text-accent:#276e48;
    --ocop-text-on-accent:#ffffff;
    --ocop-surface-product:#ffffff;
}"""

GLOBAL_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {--ocop-font: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
    color:var(--ocop-text-muted)!important;font-size:13px;opacity:1;
}
[data-testid="stApp"] :is(input,textarea)::placeholder,
[data-testid="stChatInput"] textarea::placeholder {color:var(--ocop-text-muted);opacity:1;}
html, body, [data-testid="stApp"] {
    font-family: var(--ocop-font);
    -webkit-font-smoothing: antialiased;
}
[data-testid="stApp"] :is(h1, h2, h3, h4, h5, h6, p, label, input, textarea, button, select),
[data-testid="stMarkdownContainer"],
[data-testid="stChatMessage"],
[data-testid="stChatInput"] textarea,
[data-baseweb="select"],
[data-baseweb="popover"] [role="option"],
[role="dialog"] :is(h1, h2, h3, p, label, input, textarea, button) {
    font-family: var(--ocop-font) !important;
}
[data-testid="stHeader"] {display: none;}
[data-testid="stToolbar"] {display: none;}
.block-container {
    max-width: 1210px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}
h1,h2,h3 {letter-spacing:-.6px; color:#123E2B;}
#MainMenu, footer {visibility:hidden;}
.st-key-site_header .st-key-logo_home button {
    padding:0;border:0;background:transparent;color:#164c38;box-shadow:none;
    min-height:36px;justify-content:flex-start;
}
.st-key-site_header .st-key-logo_home button p {font-size:clamp(18px,2.1vw,25px);font-weight:800;white-space:nowrap;letter-spacing:-.7px;}
.st-key-site_header .st-key-logo_home button:not(:disabled):hover {
    background:transparent!important;color:var(--ocop-text-accent)!important;box-shadow:none;transform:none;
}
.st-key-site_header .st-key-logo_home button:focus-visible {outline:2px solid #39975f;outline-offset:4px;}
.st-key-site_header .brand-tagline {font-size:13px;letter-spacing:.7px;color:var(--ocop-text-muted);font-weight:700;margin:0;}
.st-key-site_header {padding:8px 0;}
.st-key-site_header [data-testid="stHorizontalBlock"] {align-items:center;gap:2rem;}
.st-key-site_header [data-testid="stColumn"] {min-width:0;}
.st-key-site_header [data-testid="stVerticalBlock"] {gap:0;justify-content:center;}
.st-key-site_header :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) {margin:0;min-width:0;max-width:100%;}
.st-key-site_header :is([data-baseweb="button-group"], [data-testid="stButtonGroupFlex"]) {width:100%;display:flex;flex-wrap:wrap;align-items:stretch;gap:4px;}
.st-key-site_header :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button {flex:1 1 auto;min-width:0;max-width:100%;height:auto;min-height:44px;padding:8px 12px;}
.st-key-site_header :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button p {white-space:normal;overflow-wrap:anywhere;font-size:13px;line-height:1.4;}
@media(max-width:900px){
    .st-key-site_header [data-testid="stHorizontalBlock"] {flex-wrap:wrap;gap:1rem;}
    .st-key-site_header [data-testid="stColumn"] {width:100%!important;flex:1 1 100%!important;}
    .st-key-site_header .st-key-logo_home button {margin-inline:auto;}
}
@media(max-width:480px){
    .st-key-site_header :is([data-baseweb="button-group"], [data-testid="stButtonGroupFlex"]) {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));}
    .st-key-site_header :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button {width:100%;}
}
.hero {background:#F7F9F1;border:1px solid #eaf0e5;border-radius:22px;padding:40px 42px;min-height:290px;margin:12px 0 24px}
.hero h1 {font-size:clamp(31px,4vw,50px);line-height:1.25;margin:13px 0;font-weight:800}
.hero h1 span {color:var(--ocop-text-accent)}
.hero p {font-size:14px;line-height:1.85;color:var(--ocop-text-muted)}
.eyebrow {font-size:13px;font-weight:800;color:var(--ocop-text-accent);letter-spacing:2px}
.info-strip {background:#eef6e9;border-radius:12px;padding:17px 18px;color:#315e40;font-size:13px;line-height:1.7;margin-top:12px}
.section-kicker{font-size:13px;letter-spacing:2px;font-weight:800;color:var(--ocop-text-accent);text-transform:uppercase;margin-top:24px}
.section-desc {font-size:13px;color:var(--ocop-text-muted);margin-top:-7px}
.product-card {border:1px solid #e5ebe3;border-radius:14px;overflow:hidden;background:var(--ocop-surface-product);margin-bottom:4px;}
.catalog-filter-chips {display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 10px;}
.catalog-filter-chip {display:inline-flex;gap:4px;align-items:center;padding:5px 10px;border:1px solid #bfd8c6;border-radius:999px;background:#eef6f0;color:#195b3e;font-size:13px;}
#catalog-results-start {display:block;scroll-margin-top:16px;}
.product-photo {width:100%;height:172px;object-fit:contain;background:var(--ocop-surface-product);display:block;padding:12px;box-sizing:border-box;border-bottom:1px solid #f0f0f0;}
.product-card-body {padding:13px 14px 14px;display:flex;flex-direction:column;gap:8px}
.product-card .product-category {height:30px;line-height:15px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.product-card .product-name {height:80.6px;min-height:0;margin:0;overflow:hidden;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow-wrap:anywhere}
.product-card .product-meta {height:38px;margin:0;display:flex;align-items:center;flex-wrap:wrap;column-gap:8px;row-gap:4px;line-height:17px;overflow:hidden}
.product-card .star-chip {display:inline-block;flex-shrink:0;white-space:nowrap}
.product-card .product-price {height:27px;line-height:27px;margin:0;white-space:nowrap}
.product-card .source-chip {height:24px;min-width:0;}
.product-category {font-size:13px;letter-spacing:.5px;color:var(--ocop-text-accent);font-weight:800;text-transform:uppercase}
.product-name {font-size:13px;font-weight:800;min-height:41px;color:var(--ocop-text-product);line-height:1.55;margin-top:6px}
.product-meta{font-size:13px;color:var(--ocop-text-muted);margin-top:5px}
.product-price{font-size:18px;color:#c62828;font-weight:800;margin:10px 0}
.product-price-detail{font-size:26px;line-height:1.4}
.star-chip {background:#fff4d9;color:#805500;font-weight:700;padding:4px 7px;border-radius:5px;font-size:12px}
.star-chip-0 {background:#f1f3f5;color:#596579}
.star-chip-4 {background:#e8f5ec;color:#216e39}
.star-chip-5 {background:#fdebec;color:#b42332}
.star-chip-detail {display:inline-block;font-size:14px;padding:6px 10px;margin:4px 0 8px}
.source-chip {display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;line-height:16px;color:#59665e}
.source-logo {width:28px;height:20px;object-fit:contain;flex-shrink:0;border-radius:3px;display:block}
.source-name {overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stat {padding:15px 18px;border:1px solid #e7ede4;border-radius:14px;background:#fff}
.stat strong{display:block;font-size:25px;color:#164c38}
.stat small{font-size:13px;color:var(--ocop-text-muted)}
.category-tile {background:#fff;border:1px solid #e3e9e5;border-radius:14px;text-align:center;padding:16px 10px;height:150px;box-sizing:border-box;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px}
.category-icon {font-size:30px;line-height:1;width:52px;height:52px;border-radius:14px;background:#f0f6f1;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.category-tile strong{display:flex;align-items:center;justify-content:center;color:#202720;font-size:13px;line-height:1.5;min-height:36px}
.region-tile{border-radius:12px;background:#f3f8f1;border:1px solid #e0ecdf;padding:16px 18px;margin:6px 0;min-height:100px;box-sizing:border-box}
.region-heading{display:flex;align-items:center;gap:8px}
.region-icon{font-size:18px;line-height:1;flex-shrink:0}
.region-name{margin:0!important;padding:0!important;font-size:17px!important;font-weight:700!important;line-height:1.4!important;color:var(--ocop-text-primary)!important}
.region-count{display:flex;align-items:baseline;gap:5px;margin-top:8px;padding-left:26px}
.region-count strong{font-size:20px;line-height:1.3;font-weight:700;color:#27583b;font-variant-numeric:tabular-nums}
.region-count span{font-size:13px;color:#59665e;font-weight:400}
.fineprint{font-size:13px;color:var(--ocop-text-muted);line-height:1.7}
[data-testid="stApp"]:has(.st-key-business_workspace){background:#f4f6f5;color:#243b30;}
.st-key-business_workspace{background:#fff;border:1px solid #dce3df;border-radius:12px;padding:24px;box-shadow:none;}
.st-key-business_workspace [data-testid="stVerticalBlock"]{gap:16px;}
.st-key-business_workspace h1{font-size:32px!important;line-height:1.25!important;font-weight:750!important;letter-spacing:-.5px;margin:0!important;padding:0 0 8px!important;}
.st-key-business_workspace h2{font-size:22px!important;line-height:1.35!important;font-weight:700!important;letter-spacing:-.2px;margin:0!important;padding:8px 0 4px!important;}
.st-key-business_workspace h3{font-size:18px!important;line-height:1.4!important;font-weight:700!important;letter-spacing:0;margin:0!important;padding:4px 0!important;}
.st-key-business_workspace :is(p,label,input,textarea,button,[data-baseweb="select"]){font-size:15px!important;line-height:1.6!important;}
.st-key-business_workspace [data-testid="stCaptionContainer"] p{font-size:14px!important;color:#52645a!important;}
.st-key-business_workspace [data-testid="stForm"]{padding:16px;border:1px solid #dce3df;border-radius:12px;background:#fff;box-shadow:none;}
.st-key-business_workspace [data-testid="stExpander"]{border:1px solid #dce3df;border-radius:10px;background:#fff;box-shadow:none;}
.st-key-business_workspace [data-testid="stExpander"] summary{padding:12px 16px;font-weight:600;}
.st-key-business_workspace [data-testid="stMetric"]{padding:12px 16px;border:1px solid #dce3df;border-radius:10px;background:#f7f9f8;}
.st-key-business_workspace [data-testid="stMetricValue"]{font-size:26px;line-height:1.3;color:#123e2b;}
.st-key-business_workspace :is(input,textarea){color:#243b30;background:#fff;}
.st-key-business_workspace :is([data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div){border:1px solid #b6c3bb;border-radius:10px;box-shadow:none;}
.st-key-business_workspace [role="tab"]{padding:8px 16px;color:#46594e;border-radius:10px 10px 0 0;}
.st-key-business_workspace [role="tab"][aria-selected="true"]{color:#14532d;background:#e5f2e9;font-weight:700;}
.st-key-business_workspace [data-baseweb="tab-highlight"]{background:#195b3e;}
.st-key-business_workspace :is(button,a,input,textarea,select,[role="tab"],[role="combobox"],summary):focus-visible{outline:3px solid #195b3e!important;outline-offset:3px!important;}
.st-key-business_workspace :is([data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]):focus-within{outline:3px solid #195b3e;outline-offset:2px;}
@media(max-width:640px){.st-key-business_workspace{padding:16px;}.st-key-business_workspace h1{font-size:28px!important;}.st-key-business_workspace h2{font-size:20px!important;}}
.st-key-account_bar{background:#f5f8f6;border:1px solid #e0e8e3;border-radius:12px;padding:10px 14px;margin-bottom:18px;}
.st-key-account_bar [data-testid="stHorizontalBlock"]{align-items:center;gap:12px;}
.account-identity{display:flex;align-items:center;flex-wrap:wrap;gap:8px;min-height:38px;font-size:14px;color:#123e2b;}
.account-name{font-weight:700;overflow-wrap:anywhere;}
.account-role{padding:3px 9px;border-radius:999px;font-size:12px;font-weight:700;background:#dcfce7;color:#166534;}
.account-role-admin{background:#ede9fe;color:#5b21b6;}
.account-role-buyer{background:#dbeafe;color:#1e40af;}
.st-key-account_bar [data-testid="stButton"] button{min-height:38px;white-space:nowrap;}
@media(max-width:640px){.st-key-account_bar [data-testid="stHorizontalBlock"]{flex-wrap:nowrap;}.st-key-account_bar [data-testid="stColumn"]:first-child{flex:1 1 0!important;min-width:0!important;width:auto!important;}.st-key-account_bar [data-testid="stColumn"]:last-child{flex:0 0 auto!important;min-width:100px!important;width:auto!important;}}
[data-testid="stButton"] button[kind="primary"] {background:#195b3e;border-color:#195b3e}
[data-testid="stButton"] button {border-radius:9px}
@media(max-width:720px){.hero{padding:22px}.product-photo{height:150px}.block-container{padding-left:1rem;padding-right:1rem}}

:is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a),
[data-testid="stChatInputSubmitButton"],a.chat-product-link,.product-card {
    transition:background-color .18s ease,border-color .18s ease,color .18s ease,box-shadow .18s ease,transform .18s ease;
}
@media(hover:hover) {
    :is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a):not(:disabled):hover,
    [data-testid="stMarkdownContainer"] a.chat-product-link:hover {
        background:#195b3e!important;border-color:#195b3e!important;color:var(--ocop-text-on-accent)!important;
        box-shadow:0 4px 10px rgba(25,91,62,.2);transform:translateY(-1px);
    }
    :is([data-testid="stButton"],[data-testid="stLinkButton"]) :is(button,a)[kind="primary"]:not(:disabled):hover {background:#103f2a!important;border-color:#103f2a!important;}
    :is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a):not(:disabled):hover p {color:inherit!important;}
    [data-testid="stChatInputSubmitButton"]:not(:disabled):hover {background:#195b3e!important;color:var(--ocop-text-on-accent)!important;border-radius:8px;}
    .product-card:hover {border-color:#a6c9b0;box-shadow:0 5px 16px rgba(18,62,43,.1);}
}
:is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a):focus-visible,
[data-testid="stChatInputSubmitButton"]:focus-visible,a.chat-product-link:focus-visible {
    outline:3px solid #287a4d!important;outline-offset:3px;
}
:is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a):not(:disabled):active,
a.chat-product-link:active {transform:translateY(0);box-shadow:none;}

@media(prefers-reduced-motion:reduce) {
    :is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a),
    [data-testid="stChatInputSubmitButton"],a.chat-product-link,.product-card {transition:none!important;transform:none!important;}
}

    .st-key-login_card {
        width:min(100%,420px)!important;max-width:420px;margin:24px auto;
        padding:26px;background:#fff;border:1px solid #dce5df;border-radius:16px;
        box-shadow:0 6px 24px rgba(18,62,43,.06);box-sizing:border-box;
    }
    .st-key-login_card [data-testid="stForm"] {border:0;padding:0;}
    .st-key-login_card h1 {text-align:center;}
    .st-key-login_card .st-key-guest_demand button {
        border:0;background:transparent;color:#195b3e;padding:6px 0;
        box-shadow:none;text-align:center;white-space:normal;
    }
    @media(max-width:480px){.st-key-login_card{padding:20px;margin:12px auto;}}
    
                [class*="st-key-quote_cards_"] [role="radiogroup"] {gap:10px;}
                [class*="st-key-quote_cards_"] [data-baseweb="radio"] {
                    display:flex;align-items:flex-start;margin:0;padding:14px 16px;
                    border:1px solid #d7e3db;border-radius:12px;background:#fff;
                }
                [class*="st-key-quote_cards_"] [data-baseweb="radio"]:has(input:checked) {
                    border:2px solid #287a4d;background:#edf7ef;
                }
                [class*="st-key-quote_cards_"] [data-baseweb="radio"]:hover {border-color:#287a4d;background:#f4f9f5;}
                [class*="st-key-quote_cards_"] [data-baseweb="radio"]:focus-within {outline:2px solid #287a4d;outline-offset:3px;}
                [class*="st-key-quote_cards_"] [data-baseweb="radio"] p {line-height:1.6;}
                

    .request-timeline {list-style:none!important;margin:12px 0 12px 8px!important;padding:0 0 0 22px!important;border-left:2px solid #d3e5d9;}
    .request-timeline li {position:relative;list-style:none;padding:0 0 22px 0;}
    .request-timeline li:last-child {padding-bottom:0;}
    .request-timeline li::before {content:'';position:absolute;left:-29px;top:5px;width:12px;height:12px;border-radius:50%;background:#287a4d;border:2px solid #fff;}
    .request-timeline-meta {display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;font-size:13px;color:#195b3e;}
    .request-timeline-meta span {font-size:13px;color:#53675b;}
    .request-timeline-content {margin-top:8px;padding:12px 14px;background:#f4f8f5;border:1px solid #e0e9e3;border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.7;}
    
    .ocop-stepper {display:flex;gap:8px;list-style:none!important;padding:0!important;margin:12px 0 20px!important;}
    .ocop-stepper .ocop-step {flex:1;display:flex;align-items:center;gap:8px;margin:0;padding:12px 10px;
        border:1px solid #e1e7e3;border-radius:10px;background:#f7f9f8;color:#64746b;font-size:13px;line-height:1.4;}
    .ocop-step-marker {display:grid;place-items:center;flex-shrink:0;width:26px;height:26px;border-radius:50%;
        background:#e7ece9;color:#58695e;font-weight:750;}
    .ocop-stepper .done {color:#216e40;background:#f0f7f2;border-color:#d2e4d8;}
    .ocop-stepper .done .ocop-step-marker {background:#287a4d;color:#fff;}
    .ocop-stepper .current {background:#e2f2e7;color:#123e2b;border:2px solid #287a4d;font-weight:800;}
    .ocop-stepper .current .ocop-step-marker {background:#195b3e;color:#fff;}
    @media(max-width:700px){.ocop-stepper{flex-direction:column;gap:6px;}.ocop-stepper .ocop-step{padding:9px 12px;}}
    
.product-photo-placeholder {display:grid;place-items:center;}
:root {color-scheme:light;}
[data-testid="stApp"] {background:#fff;color:var(--ocop-text-primary);}
[data-testid="stApp"] :is(input,textarea) {background:#fff;color:var(--ocop-text-primary);}
:is(.st-key-public_workspace,.st-key-site_header) :is(button,a,input,textarea,select,[role="tab"],[role="combobox"]):focus-visible,
a.chat-product-link:focus-visible {outline:3px solid #195b3e!important;outline-offset:3px!important;}
.st-key-public_workspace a {color:#195b3e;}
[data-testid="stButton"] button[kind="primary"] {color:#fff;}
:is(.st-key-public_workspace,.st-key-site_header) label {color:var(--ocop-text-primary);}
:is(.st-key-public_workspace,.st-key-site_header) button {font-size:14px;}
:is(.st-key-public_workspace,.st-key-site_header) button[kind="secondary"] {background:#fff;color:#195b3e;}
.st-key-site_header :is([data-testid="stSegmentedControl"],[data-testid="stButtonGroup"]) button {background:#fff;color:#195b3e;}
.st-key-site_header :is([data-testid="stSegmentedControl"],[data-testid="stButtonGroup"]) button:is([aria-pressed="true"],[aria-selected="true"]) {background:#195b3e;color:#fff;}
.st-key-site_header button p {color:inherit;}
[data-testid="stButton"] button[kind="primary"] p {color:inherit;}
"""

# Keep the font @import before all CSS rules; custom properties resolve later.
APP_STYLES = "<style>" + GLOBAL_CSS + COLOR_TOKENS + CHAT_CSS + "</style>"
