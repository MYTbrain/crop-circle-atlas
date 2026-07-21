import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve(import.meta.dirname, "..");
const dataDir = path.join(root, "data");
const outputDir = path.join(root, "outputs", "initial-build");
const previewDir = path.join(root, "tmp", "workbook-previews");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const formationsCsv = await fs.readFile(path.join(dataDir, "formations.csv"), "utf8");
const assertionsCsv = await fs.readFile(path.join(dataDir, "source_assertions.csv"), "utf8");
const summaryJson = JSON.parse(await fs.readFile(path.join(dataDir, "build_summary.json"), "utf8"));

const workbook = await Workbook.fromCSV(formationsCsv, { sheetName: "Formations" });
await workbook.fromCSV(assertionsCsv, { sheetName: "Source Assertions" });
const summary = workbook.worksheets.add("Summary");
const readme = workbook.worksheets.add("Read Me");
const formations = workbook.worksheets.getItem("Formations");
const assertions = workbook.worksheets.getItem("Source Assertions");

workbook.comments.setSelf({ displayName: "User" });

const formationRows = summaryJson.formations + 1;
const assertionRows = summaryJson.assertions.total + 1;
const colors = { dark: "#0E2825", teal: "#2A9D8F", pale: "#DDF3EE", orange: "#F4A261", ink: "#18312D", muted: "#5E746F", white: "#FFFFFF" };

for (const sheet of [formations, assertions, summary, readme]) sheet.showGridLines = false;

formations.freezePanes.freezeRows(1);
formations.freezePanes.freezeColumns(2);
formations.getRange(`A1:Z1`).format = { fill: colors.dark, font: { bold: true, color: colors.white }, wrapText: true };
formations.getRange(`A1:Z${formationRows}`).format.font = { name: "Aptos", size: 9, color: colors.ink };
formations.getRange(`A1:Z1`).format.font = { name: "Aptos Display", size: 9, bold: true, color: colors.white };
formations.getRange(`D2:F${formationRows}`).format.numberFormat = "0";
formations.getRange(`O2:P${formationRows}`).format.numberFormat = "0.00000";
formations.getRange(`R2:S${formationRows}`).format.numberFormat = "0.00";
formations.getRange("A:Z").format.columnWidth = 14;
formations.getRange("A:A").format.columnWidth = 18;
formations.getRange("B:B").format.columnWidth = 13;
formations.getRange("G:I").format.columnWidth = 20;
formations.getRange("K:N").format.columnWidth = 18;
formations.getRange("V:X").format.columnWidth = 34;
formations.tables.add(`A1:Z${formationRows}`, true, "FormationsTable").style = "TableStyleMedium2";

assertions.freezePanes.freezeRows(1);
assertions.freezePanes.freezeColumns(2);
assertions.getRange(`A1:AB1`).format = { fill: "#334E68", font: { bold: true, color: colors.white }, wrapText: true };
assertions.getRange(`A1:AB${assertionRows}`).format.font = { name: "Aptos", size: 9, color: colors.ink };
assertions.getRange(`A1:AB1`).format.font = { name: "Aptos Display", size: 9, bold: true, color: colors.white };
assertions.getRange("A:AB").format.columnWidth = 14;
assertions.getRange("B:D").format.columnWidth = 28;
assertions.getRange("O:R").format.columnWidth = 20;
assertions.getRange("AB:AB").format.columnWidth = 34;
assertions.tables.add(`A1:AB${assertionRows}`, true, "SourceAssertionsTable").style = "TableStyleMedium4";

summary.getRange("A1:F1").merge();
summary.getRange("A1").values = [["Crop Circle Atlas - Research Catalog"]];
summary.getRange("A1:F1").format = { fill: colors.dark, font: { name: "Aptos Display", size: 20, bold: true, color: colors.white }, rowHeight: 34 };
summary.getRange("A2:F2").merge();
summary.getRange("A2").values = [["Provenance-first entities, approximate locality geocodes, and orientation-safe analysis"]];
summary.getRange("A2:F2").format = { fill: colors.pale, font: { color: colors.ink, italic: true }, rowHeight: 24 };
summary.getRange("A4:A10").values = [["Distinct formations"],["Source assertions"],["Mapped locality centroids"],["United States formations"],["Earliest report year"],["Latest report year"],["Countries represented"]];
summary.getRange("B4").formulas = [[`=COUNTA('Formations'!$A$2:$A$${formationRows})`]];
summary.getRange("B5").formulas = [[`=COUNTA('Source Assertions'!$A$2:$A$${assertionRows})`]];
summary.getRange("B6").formulas = [[`=COUNT('Formations'!$O$2:$O$${formationRows})`]];
summary.getRange("B7").formulas = [[`=COUNTIF('Formations'!$J$2:$J$${formationRows},"US")`]];
summary.getRange("B8").formulas = [[`=MIN('Formations'!$D$2:$D$${formationRows})`]];
summary.getRange("B9").formulas = [[`=MAX('Formations'!$D$2:$D$${formationRows})`]];
summary.getRange("B10").values = [[summaryJson.countries]];
summary.getRange("A4:B10").format = { fill: "#F5FAF8", borders: { preset: "inside", style: "thin", color: "#CCE0DB" } };
summary.getRange("A4:A10").format.font = { bold: true, color: colors.muted };
summary.getRange("B4:B10").format = { fill: colors.pale, font: { bold: true, size: 14, color: colors.ink }, numberFormat: "#,##0" };

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
summary.getRange("A20:A23").values = [["Coordinates are GeoNames locality centroids, not field coordinates."],["A visible straight segment is not a geographic bearing."],["Projection rays require a reviewed true-north azimuth and uncertainty."],["Alignment hits are exploratory until tested against stratified null models."]];
summary.getRange("A20:F23").format = { fill: "#FFF7ED", font: { color: "#5B3413" }, wrapText: true };
summary.getRange("A:F").format.columnWidth = 18;
summary.getRange("A:A").format.columnWidth = 28;
summary.getRange("D:D").format.columnWidth = 22;
summary.freezePanes.freezeRows(2);

readme.getRange("A1:F1").merge();
readme.getRange("A1").values = [["How to use this workbook"]];
readme.getRange("A1:F1").format = { fill: colors.dark, font: { name: "Aptos Display", size: 18, bold: true, color: colors.white }, rowHeight: 32 };
readme.getRange("A3:B10").values = [
  ["Sheet", "Purpose"],
  ["Summary", "Auditable overview; formula-linked to the catalog sheets."],
  ["Formations", "One row per derived formation entity. Filter by country, year, crop, and coordinate quality."],
  ["Source Assertions", "One row per statement from a source. Use this sheet to audit merges and discrepancies."],
  ["Coordinate method", "geonames_locality_centroid means approximate town/place coordinates, never an exact field."],
  ["Images", "Third-party photos are linked at source and are not redistributed in this workbook."],
  ["Directions", "Reviewed geographic bearings live in data/orientation_observations.csv in the repository."],
  ["Reproducibility", `Generated ${summaryJson.generated_at}; source PDF SHA-256 ${summaryJson.pdf.sha256}.`],
];
readme.getRange("A3:B3").format = { fill: colors.teal, font: { bold: true, color: colors.white } };
readme.getRange("A3:B10").format.borders = { preset: "inside", style: "thin", color: "#D5E5E1" };
readme.getRange("A4:B10").format.wrapText = true;
readme.getRange("A:A").format.columnWidth = 24;
readme.getRange("B:B").format.columnWidth = 80;
readme.getRange("4:10").format.rowHeight = 34;

const summaryInspect = await workbook.inspect({ kind: "table", range: "Summary!A1:F23", include: "values,formulas", tableMaxRows: 25, tableMaxCols: 8 });
console.log(summaryInspect.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errors.ndjson);

for (const [sheetName, range] of [["Summary","A1:F23"],["Formations","A1:M25"],["Source Assertions","A1:L25"],["Read Me","A1:F10"]]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.2, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName.replaceAll(" ", "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "crop_circle_atlas.xlsx"));
console.log(`saved=${path.join(outputDir, "crop_circle_atlas.xlsx")}`);
