from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMATIONS_PATH = ROOT / "data" / "formations.csv"
IMAGES_PATH = ROOT / "web" / "data" / "formation_images.json"
OVERLAYS_PATH = ROOT / "web" / "data" / "registered_overlays.json"
SITE_CANDIDATES_PATH = ROOT / "data" / "global_source_site_candidates.csv"
ARCHIVE_PATH = ROOT / "data" / "reviewed_us_archive_image_links.json"
CSV_OUTPUT_PATH = ROOT / "data" / "overlay_production_queue.csv"
JSON_OUTPUT_PATH = ROOT / "data" / "overlay_production_queue.json"


ARCHIVE_EVIDENCE = {
    "cc_104e3b95dd75": {
        "clues": ["approximately 20 miles south of Teton City", "Bryon Parker", "Richard Nielsen"],
        "landmarks": ["field and road pattern south of Teton City"],
    },
    "cc_24e959df4a14": {
        "clues": ["Molex property", "Steve Berning farm", "Naperville soybean field"],
        "landmarks": ["Molex campus buildings", "property and field boundaries"],
    },
    "cc_2152af98e2d7": {
        "clues": ["near Seip Mound", "Paint Creek", "Bainbridge", "Ross County"],
        "landmarks": ["Seip Earthworks", "Paint Creek", "persistent road and field boundaries"],
    },
    "cc_7cdb63cfe429": {
        "clues": ["Serpent Mound", "Brush Creek", "Peebles", "Locust Grove"],
        "landmarks": ["Serpent Mound", "Brush Creek", "persistent road network"],
    },
    "cc_ae1b8ee2ae1f": {
        "clues": ["Rockville Road", "Suisun Valley Road", "Solano County"],
        "landmarks": ["Rockville Road", "Suisun Valley Road", "road intersection", "field corners"],
    },
    "cc_3fb745fb7416": {
        "clues": ["Miamisburg Mound", "source-reported formation coordinate"],
        "landmarks": ["Miamisburg Mound", "persistent roads", "field boundaries"],
    },
    "cc_64e65753ca3c": {
        "clues": [
            "Gene Smallidge farm",
            "Cottage Grove",
            "private driveway off Highway 61",
            "10992 Point Douglas Drive South",
        ],
        "landmarks": ["Highway 61", "farm buildings", "field boundaries", "tree lines"],
    },
    "cc_a20bb389770e": {
        "clues": ["Swoboda field", "Tilden", "Chippewa County"],
        "landmarks": ["roadside field boundaries"],
    },
    "cc_ad68564a4282": {
        "clues": ["junction of Cordelia Road and Hale Ranch Road", "Solano County"],
        "landmarks": ["Cordelia Road", "Hale Ranch Road", "road junction", "field corners"],
    },
    "cc_c8e2401c7fbf": {
        "clues": ["Spanish Fork barley field", "landowner property"],
        "landmarks": ["field boundaries", "roads", "buildings visible in aerial frame"],
    },
    "cc_c3c841d2f230": {
        "clues": ["highway between Port Arthur and Sabine Pass", "low wet field"],
        "landmarks": ["highway", "wire fence", "drainage pattern"],
    },
    "cc_72e3a77239de": {
        "clues": ["Northwood", "airport vicinity", "local grain elevator"],
        "landmarks": ["airport runway", "road grid", "field boundaries"],
    },
    "cc_74854ad00686": {
        "clues": ["Geneseo soybean field", "farmer Jim Stah"],
        "landmarks": ["field boundaries", "roads", "farm buildings where visible"],
    },
    "cc_d77797cdea69": {
        "clues": ["Sandyville", "Stark County"],
        "landmarks": ["roads", "field boundaries", "tree lines where visible"],
    },
    "cc_cee3a40aace5": {
        "clues": ["Huntingburg", "Dubois County wheat field"],
        "landmarks": ["roads", "field boundaries", "farm buildings where visible"],
    },
    "cc_111e3cdced4f": {
        "clues": [
            "Fresno State University Farm Laboratory",
            "48-acre harvested cornfield",
            "adjacent to State Route 168",
        ],
        "landmarks": ["State Route 168", "parallel service road", "automobile dealership"],
    },
    "cc_fba8a8655b8a": {
        "clues": [
            "Nut Tree Airport",
            "Blue Ridge Aeronautics overflight",
            "nine-house city block",
        ],
        "landmarks": ["residential street edge", "field road", "airport corridor"],
    },
    "cc_27e66142db39": {
        "clues": ["two circles at field edge", "oil rig behind circles", "Herington"],
        "landmarks": ["field edge", "road grid"],
    },
}


BLOCKED_ARCHIVE = {
    "cc_289dd87e4b7c": "Exact Coles County location was deliberately withheld by the source.",
    "cc_eb8ed861eac4": "The source says the aerial photographer could not provide the actual Northern Colorado location.",
    "cc_7e1b225d2395": "The location witness supplied no usable contact or field location.",
}


PRODUCTION_REVIEW = {
    "cc_5d34291524c4": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher's precise BNG target and wide aerial resolve one "
            "Luxenborough field using the rectangular scrub patch, road, field "
            "boundaries, and wider Salisbury Plain context. The reviewed source "
            "pages provide no defensible formation size, the wide frame includes "
            "the camera horizon, and the tight frame contains no distributed "
            "persistent ground controls. No source-photo footprint is published. "
            "Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_813dd47361b7": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 80-foot (24 metre) "
            "diameter, and same-event village, lake, pasture, field-boundary, and "
            "tramline context resolve the Woodway Bridge field. Four outer-ring "
            "controls place the tight frame, but they are crop geometry rather "
            "than independent ground control. The footprint remains unaccepted, "
            "rights-gated, and excluded from formal alignment. Explicit outcome: "
            "provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_260e8f52da4e": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 110-foot (33.5 metre) "
            "diameter, and same-flight woodland, road, boundary, and row context "
            "resolve the Hackpen Hill (3) field. Four outer-ring controls place "
            "the tight frame, but they are crop geometry rather than independent "
            "ground control. The footprint remains unaccepted, rights-gated, and "
            "excluded from formal alignment. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_044207cd1b0d": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 180-foot (55 metre) "
            "diameter, and same-flight hedgerow, town-edge, field-shape, and row "
            "context resolve the Nursteed Farm field. Four outer-ring controls "
            "place the tight frame, but they are crop geometry rather than "
            "independent ground control. The footprint remains unaccepted, "
            "rights-gated, and excluded from formal alignment. Explicit outcome: "
            "provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_a52fc2811092": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 180-foot (55 metre) "
            "diameter, and multiple same-flight views resolve the Rodfield Lane "
            "field against the woodland, road, curving boundary, houses, and rows. "
            "Four outer-ring controls place the tight frame, but they are crop "
            "geometry rather than independent ground control. The footprint remains "
            "unaccepted, rights-gated, and excluded from formal alignment. Explicit "
            "outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_b7f8add97942": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 180-foot (55 metre) "
            "diameter, and same-flight road, hedge-junction, field-boundary, "
            "woodland, and row context resolve the Longwood Warren field. Four "
            "outer-ring controls place the tight frame, but they are crop geometry "
            "rather than independent ground control. The footprint remains "
            "unaccepted, rights-gated, and excluded from formal alignment. Explicit "
            "outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_4fab9c03a8ea": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 90-foot (27.5 metre) "
            "diameter, and same-flight wide aerial resolve the Hackpen Hill formation "
            "to one field. Four formation-bound controls place the tight overhead "
            "frame around that target, but they are crop geometry rather than "
            "independent ground control. The footprint remains unaccepted, "
            "rights-gated, and excluded from formal alignment. Explicit outcome: "
            "provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_f1c8f8391487": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported minimum 300-foot (92 metre) "
            "diameter, and same-flight Cley Hill context resolve the 2017 formation "
            "field. Four outer-scallop controls place the tight overhead frame, but "
            "they are formation geometry rather than independent ground control. The "
            "footprint remains unaccepted, rights-gated, and excluded from formal "
            "alignment. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_706b58141f82": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 100-foot (30.5 metre) size, "
            "and same-flight wide and hilltop context resolve the 2020 Cley Hill "
            "formation field. Four outer-ring controls place the tight overhead frame, "
            "but they are formation geometry rather than independent ground control. "
            "The footprint remains unaccepted, rights-gated, and excluded from formal "
            "alignment. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_591f610ce045": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 200 by 200-foot (61 by 61 "
            "metre) extent, and same-flight Battlebury Hill context resolve the "
            "formation field. Four outer-loop controls place the tight overhead frame, "
            "but they are formation geometry rather than independent ground control. "
            "The footprint remains unaccepted, rights-gated, and excluded from formal "
            "alignment. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_87b940bfa1c8": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's precise BNG target, reported 36.5 by 18.25-metre extent, "
            "and same-flight wide field context resolve the Thorn Hill formation field. "
            "Four formation-bound controls place the tight overhead frame, but they "
            "are crop geometry rather than independent ground control. The footprint "
            "remains unaccepted, rights-gated, and excluded from formal alignment. "
            "Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_64e65753ca3c": {
        "processing_status": "unresolved",
        "reason": (
            "Public reporting and later farm records identify Gene Smallidge's "
            "long-term farm at 10992 Point Douglas Drive South, reached by a private "
            "driveway off Highway 61 in south Cottage Grove. The formation report says "
            "the oats design was about one-half mile from an access point behind a "
            "fence, but the only surviving 200 by 150 source photograph is a tight "
            "ground view with no persistent surrounding landmarks. The property has "
            "multiple plausible fields, so no unique field or defensible image "
            "registration is published. Explicit outcome: unresolved."
        ),
        "review_date": "2026-07-22",
    },
    "cc_a0ad8bfbb86e": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher BNG pointer and the 2015 wide aerial identify one long "
            "narrowing field between a curving farm lane and a persistent woodland "
            "belt. Eight distributed boundary controls produce a coherent non-folded "
            "projective display fit with a 20.84 metre control-fit RMSE, but that fit "
            "residual is not independent accuracy evidence. The display anchor differs "
            "from the publisher pointer by 95.4 metres, a second oblique frame did not "
            "yield a stable independent transform, and no checkpoint is held out. The "
            "record retains 110 metre uncertainty, remains excluded from formal "
            "alignment, and is rights-gated. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_c393cee1489c": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher coordinate, the named Hofer roundabout, the shopping "
            "complex, and the 2014 aerial identify the formation field north of the "
            "roundabout. Later construction substantially rebuilt the B38/L8253 "
            "interchange and approach roads. Automated feature matching retained "
            "only four spatially inconsistent matches, while the attempted manual "
            "full-frame projective fit crossed the projective horizon. The exact "
            "publisher point is retained as a reviewed candidate field, but no "
            "source-photo footprint is published. Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_9e3323a56bd8": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher's eight-digit BNG map reference resolves the reported "
            "formation to one field at Lane End Down, and the 2023 wide aerial "
            "agrees with the road, surrounding fields, and wooded boundaries. The "
            "wide frame includes the camera horizon, while the tighter ground-only "
            "frames do not contain four distributed projective controls or three "
            "defensible affine controls. Tested full-frame projective and affine "
            "fits either crossed the ground-plane horizon or produced implausible "
            "scale away from the control line. The precise publisher target is "
            "retained as a reviewed candidate field, but no source-photo footprint "
            "is published. Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_0fde23307e29": {
        "processing_status": "provisional_registration",
        "reason": (
            "The publisher's ten-digit BNG target, the reported 300-foot (91.5 "
            "metre) overall size, and same-flight wide aerials resolve the Mixon "
            "formation to the large field immediately west of the village. A "
            "near-nadir source frame is placed with four formation-extremity "
            "controls around the publisher target; the wide aerial constrains the "
            "field and approximate row-axis orientation. These are formation "
            "geometry controls rather than independent ground control, so the "
            "display footprint remains unaccepted, rights-gated, and excluded from "
            "formal alignment. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_38d9441f0182": {
        "processing_status": "provisional_registration",
        "reason": (
            "Two precise publisher BNG targets resolve the same narrow field at "
            "Etchilhampton Hill but differ by 129.63 metres. The Temporary Temples "
            "target better matches the formation's along-field position in the "
            "same-flight wide aerial and anchors a display footprint at the midpoint "
            "of its reported 180-to-200-foot size range. A 53-inlier same-flight "
            "match constrains approximate orientation, but the four footprint "
            "controls are formation geometry rather than independent ground control. "
            "The placement remains unaccepted, rights-gated, and excluded from formal "
            "alignment. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_04161b1b5a47": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher's BNG target and the 2015 wide aerial resolve the "
            "formation to the large field south of the distinctive paired masts "
            "and persistent tree grove near Stoford. The reusable landscape "
            "controls in that frame are compressed near the camera horizon, the "
            "tight frames contain formation geometry and tramlines but no "
            "distributed persistent ground controls, and the report provides no "
            "defensible ground scale. The precise field candidate is retained, but "
            "no source-photo footprint is published. Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_07b663c48cc4": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher's precise BNG target and the wide aerial identify the "
            "formation field immediately northwest of Target Wood: the woodland "
            "edge, adjoining road, hedge, and field geometry agree with current "
            "reference imagery. Stable landscape controls occupy only the distant "
            "upper portion of the oblique frame, the remaining field boundaries "
            "are outside the image, and the report provides no defensible ground "
            "scale. The 25 metre field candidate is retained, but no source-photo "
            "footprint is published. Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_35019d9ee8e3": {
        "processing_status": "provisional_registration",
        "reason": (
            "A full-frame near-nadir DJI image retains GPS, relative altitude, "
            "calibrated focal length and optical center, and gimbal pose. Its "
            "flat-local-ground ray projection places the visible formation center "
            "3.16 metres from the sub-camera point of a second near-vertical DJI "
            "frame by another contributor. The publisher BNG pointer resolves the "
            "same field but lies 43.75 metres from the image-derived center. The "
            "camera-pose footprint remains unaccepted, rights-gated, and excluded "
            "from formal alignment. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_1249f5846bfd": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher's BNG target and wide aerial resolve the report to the "
            "large arable field west of Etchilhampton village. The wide frame "
            "contains the report formation plus another formation in the same "
            "field, while the near-nadir frames contain crop geometry and tramlines "
            "but no embedded camera pose, documented scale, or distributed persistent "
            "ground controls. To avoid conflating distinct events, no source-photo "
            "footprint is published. Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_ebc33aa12a06": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher's BNG target, wide 2020 aerial, and current mosaic "
            "resolve the formation to the large pale arable field north of Stanton "
            "St Bernard. The formation is in the near foreground while reusable "
            "landscape controls are confined to the upper half of the oblique frame; "
            "the tight frames contain only crop geometry and tramlines, with no "
            "retained camera pose or documented scale. No source-photo footprint is "
            "published. Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_cee3a40aace5": {
        "processing_status": "provisional_registration",
        "reason": (
            "The 2006 Earthfiles aerial and official 2005 Indiana orthophoto "
            "independently match the Huntingburg Airport runway, hangar row, "
            "curving access road, and shielding tree grove. Seven distributed "
            "controls resolve one wheat field southwest of the grove; a held-out "
            "airport control has a 32.35 metre residual. The low-resolution oblique "
            "frame retains 60 metre uncertainty, remains excluded from formal "
            "alignment, and is rights-gated. Explicit outcome: provisional_registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_ca0e623b0480": {
        "processing_status": "candidate_field",
        "reason": (
            "The contemporaneous W-Files road-grid fit resolves the August 16 "
            "formation to the field west of North 41st Street and north of Townline "
            "Road. The two ICCRA frames show the formation, a road edge, a farmstead, "
            "and tree lines, but intervening land-use change leaves fewer than three "
            "distributed, independently defensible affine controls against current "
            "reference imagery. The 100 metre candidate-field point is retained; no "
            "source-photo footprint is published. Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_111e3cdced4f": {
        "processing_status": "candidate_field",
        "reason": (
            "Contemporaneous Fresno Bee reporting identifies a harvested 48-acre "
            "Fresno State cornfield adjacent to State Route 168, consistent with the "
            "ICCRA aerial's freeway, parallel service road, and automobile dealership. "
            "The university farm contained multiple corridor fields, and later campus "
            "construction removed or altered the strongest controls before a unique "
            "field could be independently recovered. The existing 700 metre corridor "
            "candidate is retained and the aerial remains source-only. Explicit "
            "outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_fba8a8655b8a": {
        "processing_status": "candidate_field",
        "reason": (
            "The full ICCRA report confirms the Nut Tree Airport overflight, and a "
            "higher-resolution licensed same-scene aerial resolves the residential "
            "street edge, nine-house block, field road, and complete insectoid figure. "
            "Modern reference imagery and the official 2003 Solano land-use geometry "
            "still admit multiple former airport-side fields; feature matching did not "
            "produce a unique defensible transform. The 850 metre search center is "
            "retained and no footprint is published. Explicit outcome: candidate_field."
        ),
        "review_date": "2026-07-22",
    },
    "cc_003c3da5c31b": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact 2018-06-23 publisher target, the earlier 2018-06-09 "
            "formation coordinate visible in the same wide frame, the Hackpen White "
            "Horse, and the road junction identify one candidate field. Tests across "
            "the long oblique scene produced incompatible local and terrain transforms, "
            "so no single defensible full-frame footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_5d5c33e3e3cf": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher map target, field shape, road, parking/access geometry, "
            "wooded Danebury earthworks, and multiple wide aerials identify one "
            "candidate field. Strong perspective and terrain parallax leave only the "
            "formation anchor defensible; tested projective fits were unstable, so no "
            "image footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_029cf09b5162": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Westbury map target and the road, escarpment, and White Horse "
            "scene identify one candidate field. The wide source frames are strongly "
            "oblique and the additional controls are compressed, near-collinear, or "
            "affected by terrain parallax; the near-nadir frames contain no persistent "
            "landmarks, so no image footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_70a65215ef96": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Stonehenge publisher target identifies one candidate field and "
            "the wide source aerials show the A303 scene. The road segment lacks unique "
            "distributed intersections in the source frame and the remaining views are "
            "formation-tight; no defensible third affine or fourth projective control "
            "was found, so no image footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_c125d1c37d59": {
        "processing_status": "candidate_field",
        "reason": (
            "The publisher map target and the persistent Cerne Abbas Giant, road, "
            "and field pattern identify one candidate field. The surviving source "
            "frames are strongly oblique or tightly cropped and do not expose three "
            "defensible distributed affine controls or four projective controls, so "
            "no image footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_ec30f3c01b4d": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact publisher target and the Winchester Science Centre campus, "
            "road junction, tree block, and surrounding fields identify one candidate "
            "field. Elevated-roof parallax and nearly collinear controls make the "
            "tested full-frame projective fits unstable, so no image footprint is "
            "published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_30c270c0d791": {
        "processing_status": "candidate_field",
        "reason": (
            "The Oakvale source coordinate constrains a candidate field, but the only "
            "surviving 273 by 204 source photograph is a tight ground view without "
            "persistent surrounding landmarks. It is unsuitable for a defensible "
            "image registration."
        ),
        "review_date": "2026-07-22",
    },
    "cc_8a68d8a0471b": {
        "processing_status": "unresolved",
        "reason": (
            "The Aloha coordinate is minute-rounded with approximately 1.5 km "
            "uncertainty, while the surviving aerial is tightly cropped around the "
            "formation and exposes no persistent surrounding landmarks. No unique "
            "field or defensible registration can be selected."
        ),
        "review_date": "2026-07-22",
    },
    "cc_db1599385db5": {
        "processing_status": "unresolved",
        "reason": (
            "The Bedford report and map pin constrain the Sandpit Road / Mitchell Road "
            "vicinity, but the linked archive consists of ground photographs and the "
            "reported point leaves multiple adjacent fields plausible. No unique field "
            "or image registration is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_72e3a77239de": {
        "processing_status": "clues_reviewed",
        "reason": (
            "Official North Dakota 2005 NAIP acquired 2005-07-12 confirms the "
            "Northwood Municipal / Vince Field road, runway, drainage, and farmstead "
            "context and narrows the source scene to the airport-adjacent field block. "
            "The surviving aerial controls are clustered along the drainage and canopy; "
            "full-image projective fits are unstable, so no overlay is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_ad68564a4282": {
        "processing_status": "clues_reviewed",
        "reason": (
            "Official California 2005 NAIP and the public report constrain the event to "
            "a pylon-crossed agricultural scene southeast of Fairfield. The only usable "
            "source aerial is a tight oblique frame: its two pylon controls are nearly "
            "collinear and no defensible distributed third or fourth control survives, "
            "so the field match and overlay remain unresolved."
        ),
        "review_date": "2026-07-22",
    },
    "cc_b4d637c767f9": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Waden Hill publisher target and the independently visible "
            "Silbury Hill / A4 scene identify one candidate field. The source is "
            "strongly oblique and terrain-dominated; only the formation anchor and "
            "clustered mound controls survived review. A three-control affine trial "
            "missed its held-out summit check by approximately 88 metres, so no "
            "source-frame footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_079e9ed8bea7": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Patney Bridge publisher target, railway corridor, underbridge, "
            "field edges, and farm structures identify one candidate field. The wide "
            "frames are materially oblique and the tight frames contain formation "
            "geometry without distributed persistent landmarks. Tested full-frame "
            "fits were unstable, so no source-frame footprint is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_c13a98d2fd3f": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Pepperbox Hill publisher target, red-roof shed, angled hedge "
            "corner, adjoining green field, wooded belt, and A36 context identify one "
            "candidate field. Fewer than three defensible affine or four projective "
            "controls survive across the oblique source frames; trial transforms had "
            "implausible footprints, so no source-frame overlay is published."
        ),
        "review_date": "2026-07-22",
    },
    "cc_8b6d16796ee3": {
        "processing_status": "candidate_field",
        "reason": (
            "The exact Maiden Castle publisher target, the persistent hillfort "
            "ramparts, and the surrounding field pattern identify one candidate "
            "field. The available wide aerial is strongly oblique and the usable "
            "rampart controls are terrain-sensitive and nearly collinear; a tested "
            "three-control affine fit missed the held-out rampart check by about "
            "100 metres, so no source-frame footprint is published."
        ),
        "review_date": "2026-07-22",
    },
}


CSV_FIELDS = [
    "formation_id",
    "assertion_ids",
    "event_date",
    "place",
    "region",
    "country",
    "source_report_urls",
    "source_image_urls",
    "source_image_count",
    "current_location_role",
    "current_latitude",
    "current_longitude",
    "current_coordinate_uncertainty_m",
    "source_coordinate_availability",
    "publisher_map_target_availability",
    "named_geographic_clues",
    "identifiable_persistent_landmarks",
    "source_image_dimensions",
    "display_rights",
    "publication_rights",
    "straight_component_likelihood",
    "priority_score",
    "processing_status",
    "blocker_or_rejection_reason",
    "selected_overlay_id",
    "registration_classification",
    "review_date",
]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def split_values(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def number(value: object) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def overlay_is_proper(overlay: dict) -> bool:
    return overlay.get("registration_status") in {
        "properly_registered",
        "accepted_georegistration",
        "accepted_projective_registration",
    }


def straight_likelihood(formation: dict[str, str]) -> str:
    tiers = {
        formation.get("straight_component_tier", "").lower(),
        formation.get("source_image_straight_tier", "").lower(),
    }
    if "high" in tiers:
        return "high"
    if "medium" in tiers:
        return "medium"
    if formation.get("has_straight_component") == "yes_candidate":
        return "candidate"
    return "unknown"


def build_queue() -> dict:
    formations = [row for row in load_csv(FORMATIONS_PATH) if not row.get("alias_of")]
    image_payload = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
    images_by_formation = image_payload.get("images_by_formation", {})
    overlay_payload = json.loads(OVERLAYS_PATH.read_text(encoding="utf-8"))
    overlays_by_formation: dict[str, list[dict]] = defaultdict(list)
    for overlay in overlay_payload.get("overlays", []):
        overlays_by_formation[overlay.get("formation_id", "")].append(overlay)
    site_candidates: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_csv(SITE_CANDIDATES_PATH):
        site_candidates[row.get("formation_id", "")].append(row)
    archive_payload = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    archive_by_formation = {
        row["formation_id"]: row for row in archive_payload.get("reports", [])
    }

    records: list[dict] = []
    for formation in formations:
        formation_id = formation["formation_id"]
        images = list(images_by_formation.get(formation_id, []))
        archive = archive_by_formation.get(formation_id)
        if not images and not archive:
            continue

        if archive:
            known_urls = {image.get("image_url", "") for image in images}
            for metadata in archive.get("source_image_metadata", []):
                if metadata.get("url") in known_urls:
                    continue
                images.append(
                    {
                        "image_url": metadata.get("url", ""),
                        "source_record_url": archive.get("source_record_url", ""),
                        "source_name": archive_payload.get("source_name", ""),
                        "width": metadata.get("width"),
                        "height": metadata.get("height"),
                        "rights_status": metadata.get("rights_status", ""),
                        "embedding_allowed": False,
                        "pixel_display_policy": "link_only_rights_gated",
                    }
                )

        source_report_urls = unique(
            split_values(formation.get("source_urls", ""))
            + [image.get("source_record_url", "") for image in images]
            + ([archive.get("source_record_url", "")] if archive else [])
        )
        source_image_urls = unique([image.get("image_url", "") for image in images])
        dimensions = unique(
            [
                f"{image.get('width')}x{image.get('height')}"
                for image in images
                if image.get("width") and image.get("height")
            ]
        )
        rights = unique([image.get("rights_status", "") for image in images])
        displayable = any(
            truthy(image.get("embedding_allowed"))
            or image.get("pixel_display_policy")
            in {
                "remote_source_on_explicit_user_action",
                "remote_open_license_on_explicit_user_action",
            }
            for image in images
        )
        openly_licensed = any(
            "commons" in image.get("source_name", "").lower()
            or "open" in image.get("rights_status", "").lower()
            or image.get("license_url")
            for image in images
        )

        has_site = bool(formation.get("site_latitude") and formation.get("site_longitude"))
        latitude = formation.get("site_latitude") if has_site else formation.get("latitude")
        longitude = formation.get("site_longitude") if has_site else formation.get("longitude")
        uncertainty_m = number(formation.get("site_coordinate_uncertainty_m")) if has_site else None
        if uncertainty_m is None:
            uncertainty_km = number(formation.get("coordinate_uncertainty_km"))
            uncertainty_m = uncertainty_km * 1000 if uncertainty_km is not None else None

        candidates = site_candidates.get(formation_id, [])
        methods = " ".join(
            [formation.get("site_coordinate_method", ""), formation.get("geocode_method", "")]
            + [candidate.get("coordinate_method", "") for candidate in candidates]
        ).lower()
        source_coordinate = any(
            token in methods
            for token in ("source", "gps", "google_maps", "publisher", "report_coordinate")
        )
        publisher_map_target = any(
            candidate.get("coordinate_source_url") or "google_maps" in candidate.get("coordinate_method", "")
            for candidate in candidates
        )

        evidence = ARCHIVE_EVIDENCE.get(formation_id, {})
        record_place = archive.get("place", "") if archive else formation.get("place", "")
        record_region = archive.get("region", "") if archive else formation.get("region", "")
        clues = unique(
            [record_place, formation.get("county", ""), record_region]
            + split_values(formation.get("site_search_aliases", ""))
            + list(evidence.get("clues", []))
        )
        landmarks = unique(list(evidence.get("landmarks", [])))
        if formation.get("site_search_aliases") and not landmarks:
            landmarks = split_values(formation.get("site_search_aliases", ""))

        overlays = overlays_by_formation.get(formation_id, [])
        selected_overlay = overlays[0] if overlays else None
        if selected_overlay and overlay_is_proper(selected_overlay):
            processing_status = "properly_registered"
            registration_classification = "properly_registered"
        elif selected_overlay:
            processing_status = "provisional_registration"
            registration_classification = "provisional_registration"
        elif formation_id in BLOCKED_ARCHIVE:
            processing_status = "blocked_source"
            registration_classification = ""
        elif archive:
            processing_status = "source_image_acquired"
            registration_classification = ""
        else:
            processing_status = "queued"
            registration_classification = ""

        production_review = PRODUCTION_REVIEW.get(formation_id, {})
        if production_review and not selected_overlay:
            processing_status = production_review["processing_status"]

        country_code = formation.get("country_code", "")
        site_status = formation.get("site_status", "")
        if archive:
            priority = 6000
        elif country_code == "US" and site_status in {"registered_site", "candidate_field"}:
            priority = 5000
        elif country_code == "US" and formation.get("location_role") == "locality_reference":
            priority = 4000
        elif country_code == "US":
            priority = 3000
        elif site_status in {"registered_site", "candidate_field"} or source_coordinate:
            priority = 2000
        else:
            priority = 1000
        priority += min(len(source_image_urls), 20) * 3
        priority += 90 if site_status == "registered_site" else 60 if site_status == "candidate_field" else 0
        priority += 45 if source_coordinate else 0
        priority += 45 if publisher_map_target else 0
        priority += min(len(landmarks), 8) * 5
        priority += 20 if straight_likelihood(formation) == "high" else 10 if straight_likelihood(formation) == "medium" else 0
        priority -= 500 if formation_id in BLOCKED_ARCHIVE else 0

        record = {
            "formation_id": formation_id,
            "assertion_ids": split_values(formation.get("assertion_ids", "")),
            "event_date": formation.get("date_iso", ""),
            "place": record_place,
            "region": record_region,
            "country": formation.get("country", ""),
            "source_report_urls": source_report_urls,
            "source_image_urls": source_image_urls,
            "source_image_count": len(source_image_urls),
            "current_location_role": formation.get("location_role", ""),
            "current_latitude": number(latitude),
            "current_longitude": number(longitude),
            "current_coordinate_uncertainty_m": uncertainty_m,
            "source_coordinate_availability": "yes" if source_coordinate else "no",
            "publisher_map_target_availability": "yes" if publisher_map_target else "no",
            "named_geographic_clues": clues,
            "identifiable_persistent_landmarks": landmarks,
            "source_image_dimensions": dimensions,
            "display_rights": "source_hosted_on_explicit_user_action" if displayable else "link_only_rights_gated",
            "publication_rights": "at_least_one_open_license" if openly_licensed else "not_cleared_for_redistribution",
            "straight_component_likelihood": straight_likelihood(formation),
            "priority_score": priority,
            "processing_status": processing_status,
            "blocker_or_rejection_reason": production_review.get(
                "reason", BLOCKED_ARCHIVE.get(formation_id, "")
            ),
            "selected_overlay_id": selected_overlay.get("overlay_id", "") if selected_overlay else "",
            "registration_classification": registration_classification,
            "review_date": (
                selected_overlay.get("reviewed_at", "")
                if selected_overlay
                else production_review.get("review_date", "")
                or (archive_payload.get("reviewed_at", "") if archive else "")
            ),
        }
        records.append(record)

    records.sort(key=lambda row: (-row["priority_score"], row["formation_id"]))
    status_counts = Counter(record["processing_status"] for record in records)
    return {
        "schema_version": "crop-circle-atlas/overlay-production-queue/v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "queue_basis": "Unique formation events with one or more source-image records; the 23 reviewed U.S. Crop Circle Archives matches are ranked first.",
        "unique_formation_event_count": len(records),
        "reviewed_us_archive_event_count": len(archive_by_formation),
        "reviewed_us_archive_image_count": sum(
            len(row.get("image_urls", [])) for row in archive_payload.get("reports", [])
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "records": records,
    }


def write_queue(payload: dict) -> None:
    JSON_OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with CSV_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in payload["records"]:
            writer.writerow(
                {
                    field: "; ".join(str(item) for item in record[field])
                    if isinstance(record.get(field), list)
                    else "" if record.get(field) is None
                    else record.get(field, "")
                    for field in CSV_FIELDS
                }
            )


if __name__ == "__main__":
    queue = build_queue()
    write_queue(queue)
    print(
        json.dumps(
            {
                "unique_formation_event_count": queue["unique_formation_event_count"],
                "reviewed_us_archive_event_count": queue["reviewed_us_archive_event_count"],
                "reviewed_us_archive_image_count": queue["reviewed_us_archive_image_count"],
                "status_counts": queue["status_counts"],
            },
            sort_keys=True,
        )
    )
