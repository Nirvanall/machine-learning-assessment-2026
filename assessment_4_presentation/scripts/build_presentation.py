"""Build editable PowerPoint, matching vector PDF and speaker notes from saved evidence.

Run from any directory. No model training or cloud operations.
"""
from pathlib import Path
import csv, json, math, hashlib
from importlib.metadata import version
from pptx import Presentation
from pptx.util import Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assessment_4_presentation'
EVIDENCE = ROOT / 'artifacts/steam_experiments/quick'
W,H = 960,540
BG='FAFAF7'; INK='172B2A'; MUTED='60716D'; GREEN='137A69'; PALE='E6F1EB'; LINE='D7DFD9'; GRAY='B2C0BA'; ORANGE='B06C3E'; LIGHT='F1F3EF'; WHITE='FFFFFF'
FONT_DIR=Path('/usr/share/fonts/truetype/liberation')
pdfmetrics.registerFont(TTFont('Deck',str(FONT_DIR/'LiberationSans-Regular.ttf')))
pdfmetrics.registerFont(TTFont('DeckBold',str(FONT_DIR/'LiberationSans-Bold.ttf')))
pdfmetrics.registerFont(TTFont('Code','/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'))

def rows(name):
    with (EVIDENCE/name).open() as stream:return list(csv.DictReader(stream))
TEST={r['model']:r for r in rows('final_test_metrics.csv')}
HIGH={r['model']:r for r in rows('final_test_high_owner_summary.csv')}
CV={r['model']:r for r in rows('five_fold_comparison.csv')}
CATEGORIES={(r['model'],int(r['class_id'])):r for r in rows('final_test_category_metrics.csv')}
RUN=json.loads((EVIDENCE/'run_manifest.json').read_text())
RF='Random forest'; CAT='Tuned CatBoost + engineered + tags'; TRF='Tuned random forest'; KNN='Default KNN reference'
rf=lambda metric:float(TEST[RF][metric])
# Narrative is authored for this evidence snapshot; stop if results change.
assert RUN['run_mode']=='quick' and RUN['final_model']=='Random forest'
assert RUN['final_refit_rows']==46891 and RUN['test_rows']==11723
assert math.isclose(rf('macro_f1'),0.6391785735466987,abs_tol=1e-10)
assert int(HIGH[RF]['identified_high_owner_games'])==822 and int(HIGH[RF]['false_high_owner_flags'])==505
assert '79 passed' in (ROOT/'assessment_2_production/VERIFICATION.md').read_text()
assert '34.15' in (ROOT/'assessment_2_production/VERIFICATION.md').read_text()
source_paths={
'S1':['assessment_1_modeling/notebooks/steam_eda_baseline_assessment.ipynb'],
'S2':['artifacts/steam_experiments/quick/final_test_metrics.csv','artifacts/steam_experiments/quick/five_fold_comparison.csv','artifacts/steam_experiments/quick/validation_comparison.csv'],
'S3':['artifacts/steam_experiments/quick/final_test_high_owner_summary.csv','artifacts/steam_experiments/quick/final_test_category_metrics.csv','artifacts/steam_experiments/quick/final_test_confusion_matrices.csv'],
'S4':['artifacts/steam_experiments/quick/run_manifest.json','artifacts/steam_experiments/quick/bootstrap_intervals.csv'],
'S5':['assessment_2_production/README.md','assessment_2_production/VERIFICATION.md'],
'S6':['assessment_3_infrastructure/azure-blueprint.md','assessment_3_infrastructure/release-promotion.md','assessment_3_infrastructure/containerapp.dev.template.yaml','assessment_3_infrastructure/containerapp.template.yaml'],
'S8':['assessment_4_presentation/Azure ML Production Deployment Architecture.png'],
'S7':['assessment_1_modeling/notebooks/steam_model_experiments.ipynb'],
}

prs=Presentation();prs.slide_width=Pt(W);prs.slide_height=Pt(H)
prs.core_properties.title='Steam | Better game partnership decisions'
prs.core_properties.subject='Assessment 4 — management presentation'
prs.core_properties.author='Steam ML project'
prs.core_properties.keywords='Steam, Random Forest, ONNX, FastAPI, Azure Container Apps'
pdf=canvas.Canvas(str(OUT/'steam_management_presentation_dev_prod.pdf'),pagesize=(W,H),pageCompression=1)
pdf.setTitle(prs.core_properties.title);pdf.setAuthor('Steam ML project')
slides=[]; sl=None; current=None

def rgb(hex):return RGBColor.from_string(hex)
def rect(x,y,w,h,fill=WHITE,stroke=None,radius=0):
    shape=sl.shapes.add_shape(MSO_SHAPE.RECTANGLE,Pt(x),Pt(y),Pt(w),Pt(h))
    if fill:shape.fill.solid();shape.fill.fore_color.rgb=rgb(fill)
    else:shape.fill.background()
    if stroke:shape.line.color.rgb=rgb(stroke);shape.line.width=Pt(.8)
    else:shape.line.fill.background()
    pdf.setFillColor(HexColor('#'+(fill or BG)));pdf.setStrokeColor(HexColor('#'+(stroke or BG)))
    pdf.setLineWidth(.8);pdf.rect(x,H-y-h,w,h,fill=bool(fill),stroke=bool(stroke))
    return shape

def line(x1,y1,x2,y2,color=LINE,width=1):
    shape=sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Pt(x1),Pt(y1),Pt(x2),Pt(y2))
    shape.line.color.rgb=rgb(color);shape.line.width=Pt(width)
    pdf.setStrokeColor(HexColor('#'+color));pdf.setLineWidth(width);pdf.line(x1,H-y1,x2,H-y2)

def arrow(x1,y1,x2,y2,color=MUTED):
    line(x1,y1,x2,y2,color,1.2)
    angle=math.atan2(y2-y1,x2-x1)
    for d in [-.55,.55]:
        line(x2,y2,x2-7*math.cos(angle+d),y2-7*math.sin(angle+d),color,1.2)

def wrap(s,width,size,font):
    lines=[]
    for paragraph in s.split('\n'):
        if not paragraph:lines.append('');continue
        current=''
        for word in paragraph.split(' '):
            candidate=current+' '+word if current else word
            if current and pdfmetrics.stringWidth(candidate,font,size)>width:
                lines.append(current);current=word
            else:current=candidate
        lines.append(current)
    return lines

def text(x,y,w,h,s,size=20,bold=False,color=INK,align='left',font='Arial',leading=1.15):
    pdf_font='Code' if font=='DejaVu Sans Mono' else ('DeckBold' if bold else 'Deck')
    lines=wrap(str(s),w,size,pdf_font)
    needed=size+(len(lines)-1)*size*leading
    assert needed<=h+1, f'Slide {len(slides)} text too tall: {s!r}, {needed}>{h}'
    assert 0<=x and 0<=y and x+w<=W+1 and y+h<=H+1,(x,y,w,h,s)
    for value in lines:assert pdfmetrics.stringWidth(value,pdf_font,size)<=w+1,(s,value,w)
    box=sl.shapes.add_textbox(Pt(x),Pt(y),Pt(w),Pt(h));tf=box.text_frame
    tf.clear();tf.word_wrap=False;tf.margin_left=0;tf.margin_right=0;tf.margin_top=0;tf.margin_bottom=0
    for i,value in enumerate(lines):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=value
        p.font.name=font;p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=rgb(color)
        p.space_before=Pt(0);p.space_after=Pt(0);p.line_spacing=Pt(size*leading)
        p.alignment={'left':PP_ALIGN.LEFT,'center':PP_ALIGN.CENTER,'right':PP_ALIGN.RIGHT}[align]
        pdf.setFillColor(HexColor('#'+color));pdf.setFont(pdf_font,size)
        baseline=H-y-size*.82-i*size*leading
        draw={'left':pdf.drawString,'center':pdf.drawCentredString,'right':pdf.drawRightString}[align]
        draw(x if align=='left' else x+w/2 if align=='center' else x+w,baseline,value)
    return box

def smalllabel(x,y,w,s,color=GREEN):text(x,y,w,18,s,10,True,color)
def header(kicker,title,sub=None):
    smalllabel(52,27,840,kicker.upper())
    text(52,63,856,79,title,31,True)
    if sub:text(52,132,850,24,sub,14,color=MUTED)

def footer(source,backup=False):
    line(52,500,908,500)
    text(52,510,815,17,source,8.5,color=MUTED)
    text(872,509,36,19,f'{len(slides):02}',10,True,color=MUTED,align='right')

def start(title,seconds,notes,sources,backup=False):
    global sl,current
    sl=prs.slides.add_slide(prs.slide_layouts[6])
    sl.background.fill.solid();sl.background.fill.fore_color.rgb=rgb(BG)
    pdf.setFillColor(HexColor('#'+BG));pdf.rect(0,0,W,H,fill=1,stroke=0)
    current={'title':title,'seconds':seconds,'notes':notes,'sources':sources,'backup':backup}
    slides.append(current)
    label='BACKUP — not part of the 12:30 talk' if backup else f'Target speaking time: {seconds//60}:{seconds%60:02}'
    source_text='\n'.join(f'{code}: '+', '.join(source_paths[code]) for code in sources)
    sl.notes_slide.notes_text_frame.text=f'{label}\n\n{notes}\n\nEvidence:\n{source_text}'

def end():pdf.showPage()

def takeaway(s):
    rect(52,439,856,43,PALE)
    text(68,449,823,25,s,17,True,color=GREEN)

def node(x,y,w,h,title,body,fill=WHITE):
    rect(x,y,w,h,fill,LINE)
    text(x+12,y+12,w-24,36,title,17,True,align='center')
    if body:text(x+12,y+49,w-24,h-53,body,12.5,color=MUTED,align='center')

# 01
start('Recommend a controlled internal pilot',45,
'''Open with the decision: use the fixed Random Forest as a decision-support tool for an internal pilot. The goal is to help approved teams prioritize games for partnership review. On the held-out sample, it identifies roughly two thirds of games above 100,000 estimated owners, versus about one fifth with the original KNN. This is evidence of better classification, not an estimate of extra partnerships or downloads. We have also packaged the model and designed private Azure hosting with DEV testing and approval before any PROD promotion. The choice was fixed from development results before the final comparison. I will cover what the data tells us, the business tradeoff, and what remains before a real release. The first 11 slides take 12 minutes 30 seconds, leaving 2 minutes 30 seconds for questions.''',['S2','S3','S4','S5','S6'])
smalllabel(52,35,850,'STEAM / MANAGEMENT BRIEFING')
rect(52,105,42,5,GREEN)
text(52,139,850,121,'A stronger shortlist\nfor Steam partnerships',46,True)
text(52,287,800,57,'Recommend a controlled internal pilot of the Random Forest predictor.',23,color=MUTED)
for x,value,label in [(52,'66%','High-owner games identified'),(350,'0.639','Score across all three classes'),(648,'Private','FastAPI + Azure design')]:
    line(x,384,x+250,384)
    text(x,401,250,45,value,37,True,color=GREEN)
    text(x,454,260,26,label,15,color=MUTED)
footer('Exploratory selection • historical owner bands • Azure deployment is a proposal | S2–S6');end()

# 02
start('Define exactly what we can predict',75,
'''The source contains 85,103 games. The preprocessing policy retains 58,614 games that are at least one year old at 5 July 2023 and have positive ownership midpoints. This gives titles time to accumulate ownership, but it excludes the use case of predicting a game before launch. The original owner intervals are mapped into three broad categories. The midpoint is the average of the source lower and upper bounds, used for auditing and eligibility; none of those ownership fields is a predictor. Around 71 percent of games fall in the lowest category and only 11 percent in the highest. A classifier can therefore look accurate simply by predicting low ownership. These are estimated cumulative owners, not measured downloads, unique players or revenue. The high category spans 100,000 to 200 million owners and cannot distinguish blockbusters within that group.''',['S1','S4'])
header('01 / Data scope','We estimate ownership bands for established games')
for x,value,label in [(52,'85,103','Source games'),(356,'58,614','Eligible games'),(660,'Jul 2023','Historical observation date')]:
    text(x,177,255,54,value,37,True);text(x,239,255,29,label,17,color=MUTED)
arrow(284,204,326,204,GREEN)
smalllabel(52,298,850,'OWNER-BAND DISTRIBUTION')
shares=[41595/58614,10672/58614,6347/58614];xx=52
for share,color,label in zip(shares,[GREEN,'70A596','B8D0C3'],['71%','18%','11%']):
    ww=856*share;rect(xx,328,ww,44,color);text(xx,337,ww,28,label,21,True,color=WHITE,align='center');xx+=ww
for x,label,count in [(52,'Below 20k','41,595 games'),(356,'20k to below 100k','10,672 games'),(660,'100k+','6,347 games')]:
    text(x,386,260,26,label,18,True);text(x,416,260,24,count,16,color=MUTED)
footer('Age ≥1 year; positive ownership midpoint. Estimated owners are a proxy for adoption. | S1, S4');end()

# 03
start('Translate EDA into model decisions',60,
'''Three EDA findings shape the approach. First, higher-owner games tend to have been on sale longer: median ages are 3.54, 5.14 and 6.64 years across the three bands. That is an association with accumulated ownership, not proof that age causes success. Second, prices and achievement counts are skewed, so raw numeric distances are a poor starting point for nearest neighbors. Third, the selected baseline fields have no missing values and duplicate checks pass, but clean data is not enough: we must exclude ownership and engagement outcomes from predictors and learn data-dependent preprocessing only within training folds. Missing Steam scores exist but are excluded. Together with imbalance, these findings explain why we use class-balanced reporting and compare tree models rather than trust headline accuracy. The historical split still cannot validate performance on future releases.''',['S1'])
header('02 / EDA findings','The data explains why the original baseline struggles')
cols=[52,348,644]
smalllabel(cols[0],177,250,'TIME ON THE MARKET')
text(cols[0],207,250,50,'Higher-owner games\ntend to be older',22,True)
for i,(label,val) in enumerate([('<20k',3.54),('20k–<100k',5.14),('100k+',6.64)]):
    y=285+i*34;text(52,y,92,24,label,13,color=MUTED);rect(147,y+3,130*val/7,15,GREEN if i==2 else GRAY);text(282,y-1,44,24,f'{val:.2f}',14,True)
text(52,398,260,25,'Median game age, in years',13,color=MUTED)
line(327,180,327,420);line(623,180,623,420)
smalllabel(cols[1],177,250,'UNEVEN FEATURE SCALES')
text(cols[1],207,250,50,'Price + achievements\nhave long tails',22,True)
text(cols[1],285,250,111,'Large values distort\nunscaled KNN distances.\n\nTest scaling and trees.',17,color=MUTED)
smalllabel(cols[2],177,250,'QUALITY AND INPUT CONTROL')
text(cols[2],207,250,50,'Audit passed;\nkeep outcomes out',22,True)
text(cols[2],285,250,115,'No duplicate records or missing baseline inputs.\n\nOwner and engagement outcomes stay excluded.',17,color=MUTED)
takeaway('Evaluate all bands; fit learned preprocessing inside training folds.')
footer('Descriptive associations are not causal effects. Coverage is limited to the processed sample. | S1');end()

# 04
start('Explain the experiment logic',75,
'''We first reproduce the default KNN and compare it with a majority-class reference. Then we tune and scale KNN to check whether the original algorithm can improve. KNN votes using the most similar games. Random Forest averages many decision-rule trees, testing nonlinear interactions without relying on numeric distance. CatBoost builds trees sequentially to reduce errors, giving us a different learning strategy. Its fixed-setting feature ladder adds engineered metadata, then tags and description text. Hyperparameter searches follow so we can distinguish representation changes from tuning. Every learned imputer and vocabulary is fitted within the training folds. Five-fold evaluation repeats the check: in each round the model learns from four portions and is evaluated on the remaining portion. Keeping the category mix similar checks consistency without rewarding only the largest class. Selection was exploratory: development was capped at 6,000 games, with 4,500 initial training and 1,500 validation games. Final candidate models were refitted on all 46,891 non-test games, then reported on the same 11,723 test games. The frozen Random Forest family won the earlier validation comparison; tuning did not improve its paired development CV macro F1.''',['S2','S4','S7'])
header('03 / Modeling approach','Improve the reference, then test richer alternatives')
items=[(52,178,'1  Establish the reference','Default KNN + majority predictor','Does the model beat class imbalance?'),(496,178,'2  Improve the original learner','Scaled and tuned KNN','Can better neighbors fix the weaknesses?'),(52,306,'3  Compare tree models','Random Forest and CatBoost','Can nonlinear interactions add signal?'),(496,306,'4  Add features, then tune','Engineering → tags/text → searches','Does each extra step justify its cost?')]
for x,y,t,a,b in items:
    rect(x,y,412,112,WHITE,LINE);text(x+16,y+13,380,29,t,20,True);text(x+16,y+49,380,24,a,16,color=GREEN);text(x+16,y+80,380,20,b,13,color=MUTED)
text(52,444,856,38,'5-fold checks  •  6,000-game selection sample  •  11,723-game final holdout',18,True,color=GREEN)
footer('Quick-mode selection; final refit uses 46,891 non-test games. No test-based tuning. | S2, S4, S7');end()

# 05
start('Present the model comparison without overstating the winner',75,
'''This is the final held-out comparison, not the smaller development-fold comparison. Macro F1 summarizes the balance of precision and recall across categories, giving each category equal weight. The fixed Random Forest improves from 0.467 for default KNN to 0.639, an absolute gain of 0.172. Tuned CatBoost with engineered features and tags also rounds to 0.639, while tuned Random Forest scores 0.633. We should not claim that the tiny forest/CatBoost difference proves a superior family. We retain the forest chosen from development evidence and keep CatBoost as a credible challenger. In the saved notebook benchmark, forest batch prediction costs about 0.016 milliseconds per game versus 0.883 for KNN, roughly 55 times lower. That benchmark includes pipeline preprocessing, but is not single-request HTTP latency or ONNX deployment performance. Adding TF-IDF descriptions reduced development CV macro F1 and increased cost, so more features were not automatically helpful.''',['S2','S4'])
header('04 / Held-out results','Tree models deliver the strongest class-balanced scores','Macro F1: higher is better; all three ownership classes count equally')
models=[('Majority reference','Majority reference'),('Default KNN',KNN),('Random Forest',RF),('Tuned CatBoost + tags',CAT),('Tuned Random Forest',TRF)]
for i,(label,key) in enumerate(models):
    yy=190+i*50;value=float(TEST[key]['macro_f1'])
    text(52,yy,220,27,label,17,bold=key==RF)
    rect(282,yy+3,300,19,LIGHT);rect(282,yy+3,300*value,19,GREEN if key==RF else GRAY)
    text(598,yy-3,76,29,f'{value:.3f}',22,key==RF,color=GREEN if key==RF else INK)
line(699,184,699,440)
text(731,189,177,51,f'+{rf("macro_f1")-float(TEST[KNN]["macro_f1"]):.3f}',39,True,color=GREEN)
text(731,247,177,57,'Macro F1 gain\nover KNN',18,color=MUTED)
text(731,330,177,42,'~55×',34,True,color=GREEN)
text(731,378,177,55,'Lower batch inference\ncost per game',16,color=MUTED)
text(52,458,856,26,'RF and CatBoost match to 3 decimals; retain the development-selected forest.',16,True,color=GREEN)
footer('Same 11,723 test games. Batch CPU timing includes preprocessing; it is not API latency. | S2, S4');end()

# 06
start('Make the high-owner tradeoff explicit',90,
'''The business priority changes the interpretation. Among 1,243 actual high-owner test games, default KNN finds 263, or 21 percent. The fixed forest finds 822, or 66 percent, identifying 559 additional high-owner games in this sample. But it also creates 505 false high-owner flags, compared with 90 for KNN; precision falls from about 75 to 62 percent. This is a more useful discovery tool only if the review team can absorb that workload. Tuned CatBoost finds 837 with 517 false flags. Tuned Random Forest finds 844 but produces 646 false flags. Compared with the fixed forest, tuning buys 22 extra correct flags at the cost of 141 extra false flags. The key management input is the acceptable balance between missed popular games and unnecessary review. These are classification opportunities, not measured lost partnerships or conversion revenue. Define any revised decision rule on development data, then verify it on a fresh untouched holdout.''',['S3'])
header('05 / Business impact','Find more popular games—and plan the review workload')
text(52,176,385,71,'21% → 66%',48,True,color=GREEN)
text(52,253,405,48,'High-owner recall: KNN → Random Forest',18,color=MUTED)
text(514,182,394,83,'559 more high-owner games identified on the same test sample',24,True)
smalllabel(52,315,856,'ACTUAL HIGH-OWNER GAMES: 1,243  |  HIGH-OWNER = 100k+ ESTIMATED OWNERS')
xx=[52,370,530,690];widths=[310,150,150,218]
for x,w,v in zip(xx,widths,['Candidate','Found','Missed','False flags']):text(x,345,w,26,v,16,True,color=MUTED)
for i,(label,key) in enumerate([('Random Forest',RF),('Tuned CatBoost + tags',CAT),('Tuned Random Forest',TRF)]):
    y=382+i*33
    if key==RF:rect(44,y-4,864,31,PALE)
    vals=[label,str(int(HIGH[key]['identified_high_owner_games'])),str(int(HIGH[key]['missed_high_owner_games'])),str(int(HIGH[key]['false_high_owner_flags']))]
    for x,w,v in zip(xx,widths,vals):text(x,y,w,25,v,17,bold=key==RF,color=GREEN if key==RF else INK)
footer('RF precision: 61.9% vs KNN 74.5%. More coverage comes with more false flags. | S3');end()

# 07
start('Show the simple product interface and packaging',75,
'''A business application submits a JSON record using the original CSV field names, such as AppID, Name, Release date, Price, Genres and Tags. Python preprocessing parses those values, validates eligibility and uses the fitted medians and vocabularies. AppID, Name and ownership/engagement fields do not enter classification; media URLs are not fetched. The ONNX Random Forest returns a compact JSON response with success, predicted owner band, the winning class probability and model version. The example values on the slide are illustrative. The probability is not automatically a calibrated confidence guarantee. We package the ONNX graph, preprocessing JSON and version/checksum manifest with FastAPI in a Docker image. No training or Python pickle loading happens in serving. The model only supports the three trained broad bands: it cannot truthfully return the narrower 20,000 to 50,000 source interval. Game age defaults to the model's historical observation date unless a reference date is explicitly supplied.''',['S5'])
header('06 / Production interface','One record in. One versioned prediction out.')
for x,title,body in [(52,'Raw JSON','Original CSV field names'),(270,'Python\npreprocessing','Validate • impute • encode'),(488,'ONNX\nRandom Forest','CPU inference'),(706,'Prediction','Range • probability • version')]:
    node(x,182,202,121,title,body)
for a,b in [(254,270),(472,488),(690,706)]:arrow(a+2,242,b-2,242,GREEN)
rect(52,337,548,139,INK)
code='''{
  "is_success": true,
  "predicted_owner_range": "20000 - 100000",
  "probability": 0.64,
  "model_version": "steam-rf-onnx-v1"
}'''
text(69,351,515,117,code,13,color=WHITE,font='DejaVu Sans Mono',leading=1.25)
smalllabel(640,340,268,'ONE IMMUTABLE RELEASE')
text(640,371,268,92,'Model + preprocessing\nVersion + checksum manifest\nFastAPI + Docker image',17,color=MUTED,leading=1.45)
footer('Illustrative response. Probability refers to the predicted class; calibration is not guaranteed. | S5');end()

# 08
start('Deploy to DEV, then promote the approved release',90,
'''The supplied architecture introduces a deliberate separation between development and production. We adopt that lifecycle: local model work goes through protected source and CI tests, ONNX parity checks, one image build and a security scan. Publish the candidate to private DEV ACR and its bundle to DEV Blob, then deploy to a separate internal DEV Container Apps environment. ML engineers debug through DEV-authorized clients. Acceptance checks include preprocessing/predictions, invalid inputs, identity restrictions, private reachability, load, replica failure and rollback. Any fix produces a new candidate and repeats DEV checks. Only a successful report and independent manual approval unlock production deployment credentials. Promote the same tested image digest and model bytes; do not rebuild or retrain between environments. PROD has separate resource group/network, clients, runtime identity, private registry, artifact archive and monitoring. It starts with two replicas and can scale to four. The implementation bundles the model into the image; Blob is the versioned release archive, not a natively mounted runtime filesystem. Keep JSON preprocessing, not the reference picture's joblib. No cloud environment or pipeline is actually deployed.''',['S6','S8'])
header('07 / Azure deployment lifecycle','Test in DEV. Approve. Promote the same release.')
node(52,166,245,88,'Model + source','ONNX + preprocessing JSON')
node(354,166,245,88,'CI checks + build','Tests • parity • security scan')
node(661,166,247,88,'Private DEV ACR','One immutable candidate digest')
arrow(300,210,350,210,GREEN);arrow(602,210,657,210,GREEN)
# Registry feeds DEV only. Production is reachable only through the acceptance/approval gate.
line(784,257,784,267,GREEN,1.2);line(784,267,229,267,GREEN,1.2);arrow(229,267,229,282,GREEN)
rect(52,285,355,151,PALE,LINE)
smalllabel(68,298,322,'DEV / ENGINEERING + INTERNAL TESTING')
text(68,328,322,25,'Private Container Apps',20,True)
text(68,361,322,59,"Debug • integration • access • load tests\nDEV Blob + ACR + monitoring\nSeparate DEV network and identities",14,color=MUTED,leading=1.35)
rect(430,326,100,69,WHITE,LINE)
text(439,341,82,45,"Tests pass\n+ approval",15,True,color=GREEN,align='center')
arrow(411,360,426,360,GREEN);arrow(534,360,549,360,GREEN)
rect(553,285,355,151,PALE,LINE)
smalllabel(569,298,322,'PROD / AUTHORIZED BUSINESS TEAMS')
text(569,328,322,25,'Same tested image + model',20,True)
text(569,361,322,59,"Private Container Apps • 2–4 replicas\nPROD Blob + ACR + alerts\nHealth checks • canary • rollback",14,color=MUTED,leading=1.35)
text(52,459,856,27,'No direct CI → PROD path. Separate access; promote only approved artifacts.',17,True,color=GREEN)
footer('Design only. Blob archives release files; serving loads ONNX + JSON already inside the image. | S6, S8');end()

# 09
start('Separate local verification from cloud readiness',60,
'''The implementation is more than an architecture sketch. Seventy-nine tests passed, including the CSV input contract, ONNX behavior, validation, authorization and artifact rejection. The forest was refitted on the recorded 46,891 non-test games and converted; 1,500 representative non-test examples matched its original class predictions, with a maximum probability difference around 0.00000024. The container ran as a non-root user with a read-only filesystem and no external network or published ports. All 100 local prediction calls succeeded at concurrency two; p95 HTTP loopback latency was about 34 milliseconds. These numbers do not establish an Azure SLO or live Entra integration: authentication was explicitly disabled for that isolated container check, while auth behavior was tested separately. Before a business pilot, provision the separate private environments and identities, deploy into DEV, run debugging/integration/burst/failover checks, and require independent approval. Then promote the same image/model to PROD and verify readiness, monitoring and rollback. Local tests are not evidence that those cloud stages have already run.''',['S5','S6'])
header('08 / Delivery evidence','Locally verified; deploy to DEV before PROD')
smalllabel(52,177,405,'IMPLEMENTED AND CHECKED')
for x,val,label in [(52,'79','Automated tests passed'),(274,'1,500','ONNX parity examples')]:
    text(x,214,210,53,val,39,True,color=GREEN);text(x,276,210,45,label,16,color=MUTED)
rect(52,342,407,113,PALE)
text(70,358,371,43,'100 / 100 successful calls',27,True,color=GREEN)
text(70,405,371,38,'34 ms p95 in the local container',18,color=MUTED)
line(487,177,487,458)
smalllabel(519,177,389,'BEFORE A REAL PILOT')
for i,(title,body) in enumerate([('Deploy to private DEV first','Separate network, clients and identities'),('Debug and pass DEV acceptance','API, access, load, failure and rollback'),('Approve, then promote to PROD','Same image/model digest; controlled cutover')]):
    y=214+i*83;text(519,y,389,27,title,21,True);text(519,y+34,389,37,body,16,color=MUTED)
footer('Local burst: concurrency 2, 1 CPU. Live Azure, Entra and failover behavior are not verified. | S5, S6');end()

# 10
start('Prioritize future development by value and cost',60,
'''First improve the use of current data. Full-development learning curves/tuning can test whether quick-mode selection left performance on the table. Agree on the cost of missed popular games versus false flags, then use properly separated development data for probability calibration and the high-owner decision rule. Diagnose errors, especially the middle category, and test existing engineered inputs in the forest plus the additional metadata candidates. A small RF/CatBoost ensemble is worth trying only if out-of-fold errors are complementary. Then consider frozen screenshot embeddings cached offline, followed by sampled trailer frames and video encoders only if they add repeatable value relative to extraction/storage costs. For the product, keep humans in the review loop and collect delayed owner outcomes to monitor quality. Since current test results have now informed improvements, obtain a fresh holdout and chronological/grouped validation before stronger forecasting claims.''',['S7','S6'])
header('09 / Roadmap','Improve decision value before adding compute cost')
for x,kicker,title,body in [
(52,'FIRST','Strengthen the current model','Full-development evaluation\nCalibrate and test decision rules\nFresh, untouched final validation'),
(348,'NEXT','Target the remaining errors','Forest + engineered metadata\nReview middle-band mistakes\nTest complementary ensembles'),
(644,'THEN','Explore visual evidence','Cached screenshot embeddings\nSampled trailer frames\nVideo only if gains justify cost')]:
    smalllabel(x,180,260,kicker);text(x,216,260,62,title,24,True)
    line(x,291,x+260,291)
    text(x,320,260,111,body,18,color=MUTED,leading=1.45)
takeaway('Keep human review; monitor missed games, false flags and drift after launch.')
footer('Proposed experiments, not implemented gains. Learn every new policy on development data. | S7, S6');end()

# 11
start('Ask managers for concrete decisions',45,
'''Close with a bounded recommendation rather than a claim that the system is finished. The fixed forest offers a substantially better starting point for finding high-owner games than KNN, with a simple and tested serving path. Ask managers to agree on the acceptable false-flag workload and missed-opportunity rate, name owners for DEV testing, independent release approval and ongoing model monitoring, and require the DEV acceptance and fresh-validation gates before PROD business use. Treat this as review support; do not promise more downloads or successful partnerships from offline classification metrics. The CatBoost challenger and staged roadmap remain available if new evidence justifies a change. Pause here for questions. Backup slides contain exact metrics, per-category errors and evidence sources. Budget two minutes thirty seconds for questions within the fifteen-minute meeting.''',['S2','S3','S5','S6','S7'])
header('10 / Recommendation','Approve a gated internal pilot')
for i,(num,title,body) in enumerate([
('01','Agree the business tradeoff','How many false flags can the review team handle?'),
('02','Assign DEV test and PROD approval owners','Who reviews test evidence and authorizes promotion?'),
('03','Promote only after DEV acceptance','Same tested release, rollback plan and fresh model validation.')]):
    y=181+i*91;text(52,y,65,48,num,31,True,color=GREEN);text(142,y,766,32,title,25,True);text(142,y+40,766,32,body,18,color=MUTED)
text(52,465,856,25,'Discussion / 2 min 30 sec',16,True,color=GREEN)
footer('Recommendation: DEV first; approved PROD pilot only after acceptance and release gates. | S2–S7');end()

# 12 BACKUP
start('Backup — exact test metrics',0,
'''Use only if asked. These are the same held-out games, with quick-mode development selection and full non-test refitting. Macro F1 gives equal weight to all three classes. Balanced accuracy averages class recalls. Inference milliseconds per game are amortized across the 11,723-row batch in the saved sklearn pipeline benchmark, not ONNX HTTP serving. The forest/CatBoost macro-F1 difference is approximately 0.00012 and should not be treated as evidence of a meaningful superiority. The bootstrap interval for the selected forest's macro F1 is roughly 0.628 to 0.649; its paired improvement versus KNN is roughly 0.159 to 0.187. These intervals condition on the fitted models and this random test sample, not retraining or future data shift.''',['S2','S3','S4'],True)
header('BACKUP / Model detail','Exact results on the held-out sample','Selection: quick mode • Final refit: 46,891 games • Test: 11,723 games')
colx=[52,327,442,557,676,791];colw=[265,105,105,109,105,117]
for x,w,v in zip(colx,colw,['Model','Macro F1','Balanced\naccuracy','100k+\nrecall','100k+\nprecision','Batch ms\nper game']):text(x,179,w,50,v,14,True,color=MUTED)
for i,(label,key) in enumerate([('Default KNN',KNN),('Random Forest',RF),('Tuned CatBoost + tags',CAT),('Tuned Random Forest',TRF)]):
    y=249+i*49
    if key==RF:rect(44,y-8,864,43,PALE)
    hr=CATEGORIES[(key,2)]
    vals=[label,f'{float(TEST[key]["macro_f1"]):.4f}',f'{float(TEST[key]["balanced_accuracy"]):.4f}',f'{float(hr["recall"]):.1%}',f'{float(hr["precision"]):.1%}',f'{float(TEST[key]["inference_ms_per_game"]):.4f}']
    for x,w,v in zip(colx,colw,vals):text(x,y,w,29,v,16,bold=key==RF)
text(52,458,856,26,'Forest macro F1: 95% bootstrap interval 0.628–0.649 (test-sample uncertainty only).',16,color=MUTED)
footer('All values from saved experiment artifacts; timing is local and batch-amortized. | S2, S3, S4',True);end()

# 13 BACKUP
start('Backup — forest confusion matrix',0,
'''Rows are actual categories; columns are predicted categories. The forest identifies 7,344 of 8,308 low-owner games, 816 of 2,172 middle-owner games, and 822 of 1,243 high-owner games. The middle class remains hardest, with recall about 37.6 percent. In the high-owner row, 188 games are severely underestimated into the lowest band and 233 into the middle band. Thus 421 high-owner games are missed in total. Of 1,327 high-owner predictions, 505 are false flags, producing 61.9 percent precision. Category distances are not errors in owner counts, since bands have unequal widths. This matrix helps target development error analysis, but after examining it we need fresh evaluation for follow-up changes.''',['S3'],True)
header('BACKUP / Category detail','The middle ownership band remains the hardest')
labels=['<20k','20k–<100k','100k+']; x0=220;y0=235;cw=130;ch=67
text(219,170,390,25,'PREDICTED OWNER BAND',11,True,color=MUTED,align='center')
for j,label in enumerate(labels):text(x0+j*cw,202,cw,25,label,16,True,align='center')
cm={(int(r['actual_class']),int(r['predicted_class'])):int(r['count']) for r in rows('final_test_confusion_matrices.csv') if r['model']==RF}
for i,label in enumerate(labels):
    text(52,y0+i*ch+21,152,30,label,17,True)
    for j in range(3):
        fill=GREEN if i==j else PALE if i==2 else LIGHT
        rect(x0+j*cw,y0+i*ch,cw-3,ch-3,fill)
        text(x0+j*cw,y0+i*ch+16,cw-3,39,f'{cm[i,j]:,}',25,True,color=WHITE if i==j else INK,align='center')
smalllabel(52,190,155,'ACTUAL BAND')
text(671,231,237,49,'37.6%',35,True,color=GREEN);text(671,285,237,56,'Middle-band recall',20,color=MUTED)
text(671,355,237,44,'188',33,True,color=ORANGE);text(671,399,237,65,'High-owner games placed in the lowest band',17,color=MUTED)
footer('Counts, fixed Random Forest. Actual classes are rows. Class-2 support: 1,243 games. | S3',True);end()

# 14 BACKUP
start('Backup — evidence and limits',0,
'''All numerical claims come from saved local artifacts or the documented local verification. No model was retrained for this presentation. EDA coverage and class balance come from the baseline assessment; experiment metrics, high-owner counts and selection provenance come from the quick experiment outputs. Packaging and local HTTP claims come from the current CSV API verification report. The cloud architecture is a fictional proposal, based on the assessment 3 blueprint and its Microsoft documentation links. Important constraints are the historical snapshot, three broad cumulative-owner categories, quick-mode selection and random holdout. The existing test results have been inspected; use fresh data for confirming future changes. These results do not establish causality, measured downloads, production cloud availability or additional partnership revenue.''',['S1','S2','S3','S4','S5','S6','S7'],True)
header('BACKUP / Evidence and scope','Traceable results, with explicit limits')
smalllabel(52,176,405,'EVIDENCE IN THE REPOSITORY')
for i,(code,title,body) in enumerate([
('S1','EDA and data audit','Baseline assessment notebook'),
('S2–S4','Model evidence','Final metrics, category counts, run manifest'),
('S5','Production evidence','Production README + VERIFICATION.md'),
('S6–S8','Design and improvement plans','DEV/PROD blueprint + supplied reference')]):
    y=211+i*63;text(52,y,60,25,code,15,True,color=GREEN);text(122,y,330,28,title,18,True);text(122,y+29,330,28,body,13,color=MUTED)
line(487,177,487,460)
smalllabel(519,176,389,'INTERPRETATION LIMITS')
text(519,214,389,236,'Historical cumulative-owner snapshot\n\nThree broad bands, not exact downloads\n\nQuick-mode model selection\n\nRandom holdout, not future-release proof\n\nLocal container tests; Azure design only',18,color=MUTED)
footer('Full source paths, file checksums and narrative notes accompany the editable deck.',True);end()

# 15 BACKUP — supplied reference image
start('Backup — supplied Azure architecture reference',0,
'''This is the user's supplied reference, preserved unchanged for detailed discussion. The adopted architecture follows its DEV-before-PROD lifecycle, separate environments/access, CI/CD, versioned model artifacts and monitoring. The working runtime differs in two explicit respects: preprocessing is declarative JSON rather than joblib, and model files are bundled into the tested image. Private Blob accounts archive candidate/approved bundles for the release pipeline; Container Apps does not provide a native Blob mount. A future startup downloader would require additional code and tests. The reference also shows direct user SSO; our business application authorizes teams while FastAPI validates approved machine clients. See the assessment 3 adaptation table and promotion plan for these boundaries. This image is a design reference, not deployed infrastructure.''',['S6','S8'],True)
smalllabel(52,27,856,'BACKUP / SUPPLIED ARCHITECTURE REFERENCE — ORIGINAL IMAGE')
reference=ROOT/'assessment_4_presentation/Azure ML Production Deployment Architecture.png'
from PIL import Image
with Image.open(reference) as image:
    ratio=image.width/image.height
image_h=424;image_w=image_h*ratio;image_x=(W-image_w)/2;image_y=65
sl.shapes.add_picture(str(reference),Pt(image_x),Pt(image_y),width=Pt(image_w),height=Pt(image_h))
pdf.drawImage(str(reference),image_x,H-image_y-image_h,width=image_w,height=image_h,mask='auto')
footer('Reference preserved as supplied. Adaptations: JSON preprocessing; Blob archive, not a native mount. | S6, S8',True);end()

assert sum(s['seconds'] for s in slides if not s['backup'])==750
assert len(slides)==15
prs.save(OUT/'steam_management_presentation_dev_prod.pptx');pdf.save()

# Portable presenter script, timings and evidence map.
notes=['# Steam management presentation — speaker notes','',
       '11 main slides: **12:30**. Discussion: **2:30**. Slides 12–15 are backup only.',
       '','Design: 16:9, minimal typography, one green accent, editable vector charts and diagrams.','']
elapsed=0
for i,s in enumerate(slides,1):
    if s['backup']:timing='Backup — use only if asked'
    else:
        end_time=elapsed+s['seconds'];timing=f'{elapsed//60:02}:{elapsed%60:02}–{end_time//60:02}:{end_time%60:02}';elapsed=end_time
    notes.extend([f'## {i:02}. {s["title"]}', '',f'**Timing:** {timing}','',s['notes'],'', '**Evidence:** '+', '.join(s['sources']), ''])
notes.extend(['## Evidence map',''])
for code,paths in source_paths.items():
    notes.append(f'- **{code}:** '+', '.join(f'[{Path(path).name}]({quote("../"+path, safe="/")})' for path in paths))
(OUT/'speaker_notes.md').write_text('\n'.join(notes)+'\n')
provenance={code:[{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in paths] for code,paths in source_paths.items()}
(OUT/'evidence_manifest.json').write_text(json.dumps({'main_slides':11,'backup_slides':4,'talk_seconds':750,'discussion_seconds':150,'sources':provenance},indent=2)+'\n')
(OUT/'requirements.txt').write_text('\n'.join(f'{name}=={version(name)}' for name in ['python-pptx','reportlab','pymupdf'])+'\n')
print(f'Built {len(slides)} slides: PPTX + PDF + notes + evidence manifest.')
