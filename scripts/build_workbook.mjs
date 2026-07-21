import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve(import.meta.dirname, "..");
const dataDir = path.join(root, "data");
const outputDir = path.join(root, "outputs", "initial-build");
const previewDir = path.join(root, "tmp", "workbook-previews");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const formationIndex = JSON.parse(await fs.readFile(path.join(root, "web", "data", "formation_index.json"), "utf8"));
const assertionsCsv = await fs.readFile(path.join(dataDir, "source_assertions.csv"), "utf8");
const summaryJson = JSON.parse(await fs.readFile(path.join(dataDir, "build_summary.json"), "utf8"));

const workbookFormationFields = [
  "formation_id", "date_iso", "date_precision", "year", "place", "region", "country", "country_code",
  "county", "crop", "size_text", "classification", "source_count", "source_names", "source_urls", "site_status",
  "latitude", "longitude", "geocode_method", "coordinate_uncertainty_km", "site_coordinate_method",
  "site_coordinate_uncertainty_m", "site_directly_visible", "site_alignment_eligible", "site_cluster_id",
  "site_search_aliases", "site_evidence_source_url", "site_evidence_artifact_ids",
  "site_evidence_artifact_sha256s", "site_review_status",
  "site_rights_status", "location_role", "has_straight_component", "orientation_status", "source_image_count",
  "straight_component_tier", "diagram_angle_deg", "source_image_straight_tier", "source_image_axis_deg",
  "source_image_axis_uncertainty_deg", "alias_count", "merged_alias_formation_ids",
];
function csvValue(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}
const formationsCsv = [
  workbookFormationFields.join(","),
  ...formationIndex.formations.map((row) => workbookFormationFields.map((field) => csvValue(row[field])).join(",")),
].join("\r\n");

function columnName(number) {
  let value = number;
  let name = "";
  while (value > 0) {
    value -= 1;
    name = String.fromCharCode(65 + (value % 26)) + name;
    value = Math.floor(value / 26);
  }
  return name;
}

function csvShape(csv) {
  const lines = csv.replace(/^\uFEFF/, "").trimEnd().split(/\r?\n/);
  const columns = (lines[0] || "").split(",").length;
  return { rows: lines.length, columns, endColumn: columnName(columns) };
}

const workbook = await Workbook.fromCSV(formationsCsv, { sheetName: "Formations" });
await workbook.fromCSV(assertionsCsv, { sheetName: "Source Assertions" });
const summary = workbook.worksheets.add("Summary");
const readme = workbook.worksheets.add("Read Me");
const formations = workbook.worksheets.getItem("Formations");
const assertions = workbook.worksheets.getItem("Source Assertions");

const optionalSheetSpecs = [
  ["site_resolutions.csv", "Field Site Reviews", "FieldSiteReviewsTable"],
  ["formation_alias_reviews.csv", "Alias Reviews", "AliasReviewsTable"],
  ["provisional_orientation_observations.csv", "Provisional Orientations", "ProvisionalOrientationsTable"],
  ["image_overlay_audit.csv", "Overlay Audit", "OverlayAuditTable"],
  ["straight_component_candidates.csv", "Straight Candidates", "StraightCandidatesTable"],
  ["orientation_observations.csv", "Reviewed Orientations", "ReviewedOrientationsTable"],
  ["image_assets.csv", "Image Assets", "ImageAssetsTable"],
  ["alignment_hits.csv", "Alignment Hits", "AlignmentHitsTable"],
  ["iccra_index_entries_full.csv", "ICCRA Index Entries", "IccraIndexEntriesTable"],
  ["iccra_image_links.csv", "ICCRA Image Links", "IccraImageLinksTable"],
  ["iccra_image_straight_candidates.csv", "ICCRA Image Straight Review", "IccraImageStraightCandidatesTable"],
  ["orientation_evidence_review.csv", "Orientation Evidence", "OrientationEvidenceTable"],
  ["source_expansion_assertions.csv", "Expansion Assertions", "ExpansionAssertionsTable"],
  ["source_expansion_access.csv", "Expansion Access", "ExpansionAccessTable"],
  ["source_expansion_crawl_manifest.csv", "Expansion Manifest", "ExpansionManifestTable"],
  ["source_expansion_parse_exclusions.csv", "Expansion Exclusions", "ExpansionExclusionsTable"],
];
const optionalSheets = [];
for (const [fileName, sheetName, tableName] of optionalSheetSpecs) {
  const filePath = path.join(dataDir, fileName);
  try {
    const csv = await fs.readFile(filePath, "utf8");
    const shape = csvShape(csv);
    if (!shape.columns) continue;
    await workbook.fromCSV(csv, { sheetName });
    optionalSheets.push({ sheet: workbook.worksheets.getItem(sheetName), sheetName, tableName, shape });
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

workbook.comments.setSelf({ displayName: "User" });

const formationRows = summaryJson.formations + 1;
const assertionRows = summaryJson.assertions.total + 1;
const formationShape = csvShape(formationsCsv);
const assertionShape = csvShape(assertionsCsv);
const colors = { dark: "#0E2825", teal: "#2A9D8F", pale: "#DDF3EE", orange: "#F4A261", ink: "#18312D", muted: "#5E746F", white: "#FFFFFF" };

for (const sheet of [formations, assertions, summary, readme, ...optionalSheets.map(item => item.sheet)]) sheet.showGridLines = false;

formations.freezePanes.freezeRows(1);
formations.freezePanes.freezeColumns(2);
formations.getRange(`A1:${formationShape.endColumn}1`).format = { fill: colors.dark, font: { bold: true, color: colors.white }, wrapText: true };
formations.getRange(`A1:${formationShape.endColumn}${formationRows}`).format.font = { name: "Aptos", size: 9, color: colors.ink };
formations.getRange(`A1:${formationShape.endColumn}1`).format.font = { name: "Aptos Display", size: 9, bold: true, color: colors.white };
formations.getRange(`D2:D${formationRows}`).format.numberFormat = "0";
formations.getRange(`Q2:R${formationRows}`).format.numberFormat = "0.00000";
formations.getRange(`T2:T${formationRows}`).format.numberFormat = "0.00";
formations.getRange(`V2:V${formationRows}`).format.numberFormat = "0.00";
formations.getRange(`A:${formationShape.endColumn}`).format.columnWidth = 14;
formations.getRange("A:A").format.columnWidth = 18;
formations.getRange("B:B").format.columnWidth = 13;
formations.getRange("G:I").format.columnWidth = 20;
formations.getRange("K:N").format.columnWidth = 18;
formations.getRange("V:X").format.columnWidth = 34;
formations.tables.add(`A1:${formationShape.endColumn}${formationRows}`, true, "FormationsTable").style = "TableStyleMedium2";

assertions.freezePanes.freezeRows(1);
assertions.freezePanes.freezeColumns(2);
assertions.getRange(`A1:${assertionShape.endColumn}1`).format = { fill: "#334E68", font: { bold: true, color: colors.white }, wrapText: true };
assertions.getRange(`A1:${assertionShape.endColumn}${assertionRows}`).format.font = { name: "Aptos", size: 9, color: colors.ink };
assertions.getRange(`A1:${assertionShape.endColumn}1`).format.font = { name: "Aptos Display", size: 9, bold: true, color: colors.white };
assertions.getRange(`A:${assertionShape.endColumn}`).format.columnWidth = 14;
assertions.getRange("B:D").format.columnWidth = 28;
assertions.getRange("O:R").format.columnWidth = 20;
assertions.getRange(`${assertionShape.endColumn}:${assertionShape.endColumn}`).format.columnWidth = 34;
assertions.tables.add(`A1:${assertionShape.endColumn}${assertionRows}`, true, "SourceAssertionsTable").style = "TableStyleMedium4";

for (const { sheet, tableName, shape } of optionalSheets) {
  sheet.freezePanes.freezeRows(1);
  sheet.getRange(`A1:${shape.endColumn}1`).format = { fill: "#46675F", font: { name: "Aptos Display", size: 9, bold: true, color: colors.white }, wrapText: true };
  sheet.getRange(`A1:${shape.endColumn}${shape.rows}`).format.font = { name: "Aptos", size: 9, color: colors.ink };
  sheet.getRange(`A:${shape.endColumn}`).format.columnWidth = 16;
  sheet.getRange(`${shape.endColumn}:${shape.endColumn}`).format.columnWidth = 32;
  if (shape.rows > 1) sheet.tables.add(`A1:${shape.endColumn}${shape.rows}`, true, tableName).style = "TableStyleMedium2";
}

const optionalWidthPlans = {
  "Field Site Reviews": [["A:B",24],["C:E",18],["F:F",38],["G:H",20],["I:J",28],["K:K",55],["L:M",48],["N:T",24]],
  "Alias Reviews": [["A:C",24],["D:D",32],["E:E",14],["F:F",70]],
  "Provisional Orientations": [["A:C",24],["D:H",18],["I:I",38],["J:J",55],["K:L",36],["M:U",24]],
  "Overlay Audit": [["A:C",32]],
  "Reviewed Orientations": [["A:C",24],["D:I",18],["J:L",38]],
  "Alignment Hits": [["A:B",22],["C:G",16],["H:P",23]],
  "ICCRA Index Entries": [["A:B",24],["C:C",18],["D:D",38],["F:F",34],["J:K",40]],
  "ICCRA Image Links": [["A:B",24],["C:E",38],["F:I",24]],
  "ICCRA Image Straight Review": [["A:C",24],["D:F",38],["G:J",23]],
  "Orientation Evidence": [["A:A",24],["B:D",38],["E:G",22],["H:K",34]],
  "Expansion Assertions": [["A:B",24],["C:D",38],["E:G",18]],
  "Expansion Access": [["A:B",24],["C:D",38],["E:F",22],["G:J",32],["K:L",20]],
  "Expansion Manifest": [["A:A",16],["B:B",42],["C:F",20],["G:G",22],["H:H",36],["I:J",18],["K:L",42]],
  "Expansion Exclusions": [["A:A",16],["B:D",42],["E:E",28]],
};
for (const [sheetName, plan] of Object.entries(optionalWidthPlans)) {
  const item = optionalSheets.find(candidate => candidate.sheetName === sheetName);
  if (!item) continue;
  for (const [range, width] of plan) item.sheet.getRange(range).format.columnWidth = width;
}
const expansionManifestItem = optionalSheets.find(item => item.sheetName === "Expansion Manifest");
if (expansionManifestItem) {
  expansionManifestItem.sheet.getRange(`G2:G${expansionManifestItem.shape.rows}`).format.numberFormat = "yyyy-mm-dd hh:mm:ss";
}

summary.getRange("A1:F1").merge();
summary.getRange("A1").values = [["Crop Circle Atlas - Research Catalog"]];
summary.getRange("A1:F1").format = { fill: colors.dark, font: { name: "Aptos Display", size: 20, bold: true, color: colors.white }, rowHeight: 34 };
summary.getRange("A2:F2").merge();
summary.getRange("A2").values = [["Evidence-separated field sites, locality references, unresolved reports, and orientation-safe analysis"]];
summary.getRange("A2:F2").format = { fill: colors.pale, font: { color: colors.ink, italic: true }, rowHeight: 24 };
const reviewedOrientationSheet = optionalSheets.find(item => item.sheetName === "Reviewed Orientations");
summary.getRange("A4:A16").values = [["Catalog entities (not proven distinct)"],["Source assertions"],["Field candidates / sites"],["Locality references (not sites)"],["Unresolved reports"],["United States catalog entities"],["Earliest report year"],["Latest report year"],["Countries represented"],["ICCRA assertions reconciled"],["Likely PDF straight-component entities"],["ICCRA source-image review candidates"],["Reviewed local orientation rows"]];
summary.getRange("B4").formulas = [[`=COUNTA('Formations'!$A$2:$A$${formationRows})`]];
summary.getRange("B5").formulas = [[`=COUNTA('Source Assertions'!$A$2:$A$${assertionRows})`]];
summary.getRange("B6").formulas = [[`=COUNTIF('Formations'!$P$2:$P$${formationRows},"candidate_field")+COUNTIF('Formations'!$P$2:$P$${formationRows},"corroborated_field")+COUNTIF('Formations'!$P$2:$P$${formationRows},"registered_site")`]];
summary.getRange("B7").formulas = [[`=COUNTIF('Formations'!$P$2:$P$${formationRows},"locality_reference")`]];
summary.getRange("B8").formulas = [[`=COUNTIF('Formations'!$P$2:$P$${formationRows},"unresolved")`]];
summary.getRange("B9").formulas = [[`=COUNTIF('Formations'!$H$2:$H$${formationRows},"US")`]];
summary.getRange("B10").formulas = [[`=MIN('Formations'!$D$2:$D$${formationRows})`]];
summary.getRange("B11").formulas = [[`=MAX('Formations'!$D$2:$D$${formationRows})`]];
summary.getRange("B12").values = [[summaryJson.countries]];
summary.getRange("B13").values = [[summaryJson.assertions.iccra]];
summary.getRange("B14").values = [[(summaryJson.straight_components?.high || 0) + (summaryJson.straight_components?.medium || 0)]];
summary.getRange("B15").values = [[(summaryJson.iccra_image_straight_review?.review_candidate_high || 0) + (summaryJson.iccra_image_straight_review?.review_candidate_medium || 0)]];
summary.getRange("B16").values = [[reviewedOrientationSheet ? Math.max(0, reviewedOrientationSheet.shape.rows - 1) : 0]];
summary.getRange("A4:B16").format = { fill: "#F5FAF8", borders: { preset: "inside", style: "thin", color: "#CCE0DB" } };
summary.getRange("A4:A16").format.font = { bold: true, color: colors.muted };
summary.getRange("B4:B16").format = { fill: colors.pale, font: { bold: true, size: 14, color: colors.ink }, numberFormat: "#,##0" };

summary.getRange("D4:E4").values = [["Country", "Formation count"]];
const topCountries = summaryJson.top_countries.slice(0, 12);
summary.getRange(`D5:E${4 + topCountries.length}`).values = topCountries;
summary.getRange("D4:E4").format = { fill: colors.teal, font: { bold: true, color: colors.white } };
summary.getRange(`E5:E${4 + topCountries.length}`).format.numberFormat = "#,##0";
summary.getRange(`D4:E${4 + topCountries.length}`).format.borders = { preset: "inside", style: "thin", color: "#D5E5E1" };
summary.getRange("A19:F19").merge();
summary.getRange("A19").values = [["Coordinate and orientation guardrails"]];
summary.getRange("A19:F19").format = { fill: colors.orange, font: { bold: true, color: "#2B1A08" } };
summary.getRange("A20:F23").merge(true);
summary.getRange("A20:A23").values = [["Locality references are search aids, never formation sites or alignment targets."],["A visible straight segment is not a geographic bearing."],["A reviewed true-north azimuth qualifies the local orientation, not its long-distance extension."],["All projections and alignment hits are exploratory until tested against preregistered stratified null models."]];
summary.getRange("A20:F23").format = { fill: "#FFF7ED", font: { color: "#5B3413" }, wrapText: true };
summary.getRange("A:F").format.columnWidth = 18;
summary.getRange("A:A").format.columnWidth = 42;
summary.getRange("D:D").format.columnWidth = 22;
summary.freezePanes.freezeRows(2);

readme.getRange("A1:F1").merge();
readme.getRange("A1").values = [["How to use this workbook"]];
readme.getRange("A1:F1").format = { fill: colors.dark, font: { name: "Aptos Display", size: 18, bold: true, color: colors.white }, rowHeight: 32 };
readme.getRange("A3:B28").values = [
  ["Sheet", "Purpose"],
  ["Summary", "Auditable overview; formula-linked to the catalog sheets."],
  ["Formations", "One row per derived formation entity. Filter by country, year, crop, and coordinate quality."],
  ["Source Assertions", "One row per statement from a source. Use this sheet to audit merges and discrepancies."],
  ["Field Site Reviews", "Reviewed field-level overrides with coordinates, uncertainty, evidence, review status, and rights status kept separate."],
  ["Alias Reviews", "Accepted duplicate-report decisions; source assertions remain preserved after entity merges."],
  ["Location work queue (repository CSV)", "All 7,745 entities prioritized for exact-field research, with unresolved and locality-reference states retained."],
  ["Provisional Orientations", "Registered but not independently checkpointed axes. These are excluded from formal alignment statistics."],
  ["Overlay Audit", "Packaged versus remote-linked overlay decisions and fail-closed reasons."],
  ["Straight Candidates", "Automated diagram detections with confidence and diagram-space angles; these are not true-north bearings."],
  ["Reviewed Orientations", "Documented local true-north bearings. Long-distance projections remain experimental and have no demonstrated predictive validity."],
  ["Image Assets", "Rights and 4-12 point registration metadata for aerial-image overlays."],
  ["Alignment Hits", "Centerline corridor intersections from experimental projections, with coordinate and bearing uncertainty eligibility."],
  ["ICCRA Index Entries", "Every parsed ICCRA index occurrence and its reconciled assertion identity."],
  ["ICCRA Image Links", "Rights-aware inventory of source-page images; cached pixels are not public workbook content."],
  ["ICCRA Image Straight Review", "Metadata-only automated review queue for ICCRA source images. Axes are image-space only, unvalidated, and never true-north bearings."],
  ["Orientation Evidence", "Reviewed source passages, including qualified bearings and explicit exclusions."],
  ["Expansion Assertions", "Metadata-only event rows from the bounded public archive pass. New normalized keys are not automatically proven-new formations."],
  ["Expansion Access", "Robots, rights, and explicit access boundaries for every evaluated expansion source."],
  ["Expansion Manifest", "One hashed row per bounded HTML or robots request; no image or membership/API requests."],
  ["Expansion Exclusions", "Five Connector anchors excluded from assertion output with an explicit reason and preserved source text."],
  ["Coordinate method", "geonames_locality_centroid means approximate town/place coordinates, never an exact field."],
  ["GeoNames attribution", "Locality coordinates use GeoNames under CC BY 4.0: https://www.geonames.org/"],
  ["Images", "Third-party photos are not redistributed. The KMZ packages zero image files and carries six disabled remote source links."],
  ["Directions", "Reviewed geographic bearings live in data/orientation_observations.csv in the repository."],
  ["Reproducibility", `Generated ${summaryJson.generated_at}; source PDF SHA-256 ${summaryJson.pdf.sha256}.`],
];
readme.getRange("A3:B3").format = { fill: colors.teal, font: { bold: true, color: colors.white } };
readme.getRange("A3:B28").format.borders = { preset: "inside", style: "thin", color: "#D5E5E1" };
readme.getRange("A4:B28").format.wrapText = true;
readme.getRange("A:A").format.columnWidth = 24;
readme.getRange("B:B").format.columnWidth = 80;
readme.getRange("4:28").format.rowHeight = 34;

const summaryInspect = await workbook.inspect({ kind: "table", range: "Summary!A1:F23", include: "values,formulas", tableMaxRows: 25, tableMaxCols: 8 });
console.log(summaryInspect.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errors.ndjson);

const renderRanges = [["Summary","A1:F23"],["Formations","A1:M25"],["Source Assertions","A1:L25"],["Read Me","A1:F28"]];
for (const { sheetName, shape } of optionalSheets) renderRanges.push([sheetName, `A1:${columnName(Math.min(shape.columns, 12))}${Math.min(shape.rows, 25)}`]);
for (const [sheetName, range] of renderRanges) {
  const preview = await workbook.render({ sheetName, range, scale: 1.2, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName.replaceAll(" ", "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "crop_circle_atlas.xlsx"));
console.log(`saved=${path.join(outputDir, "crop_circle_atlas.xlsx")}`);
