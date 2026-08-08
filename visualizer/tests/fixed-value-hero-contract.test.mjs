import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import test from "node:test";

const expectedLiteralDigest =
  "830ef59c3454d13324e6841d466a702ef3e168bab7615bb4043d6e6d58e8fd66";
const expectedArcColumns = Array.from({ length: 11 }, (_, index) => index + 17);

async function loadFiber() {
  const [encoded, manifestEncoded] = await Promise.all([
    readFile(
      new URL("../public/evidence/fixed-value-fiber-193.json", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL(
        "../public/evidence/fixed-value-fiber-193.manifest.json",
        import.meta.url,
      ),
      "utf8",
    ),
  ]);
  return {
    encoded,
    fiber: JSON.parse(encoded),
    manifest: JSON.parse(manifestEncoded),
  };
}

test("the first-load evidence contains the mechanically selected 193-form fiber", async () => {
  const { encoded, fiber, manifest } = await loadFiber();
  assert.ok(
    Buffer.byteLength(encoded) < 100_000,
    "the first-load fiber must stay below 100 KB",
  );
  assert.equal(fiber.schema_version, "partizan.fixed_value_fiber_193.v1");
  assert.equal(
    manifest.schema_version,
    "partizan.fixed_value_fiber_193.publication.v1",
  );
  assert.equal(manifest.artifact.file, "fixed-value-fiber-193.json");
  assert.equal(manifest.artifact.bytes, Buffer.byteLength(encoded));
  assert.equal(fiber.selection.target_formal, "{0|1}");
  assert.equal(fiber.selection.target_label, "1/2");
  assert.equal(fiber.selection.literal_game_sha256, expectedLiteralDigest);
  assert.equal(fiber.selection.observed_quotient_forms, 193);
  assert.equal(fiber.selection.largest_group_tie_count, 1);
  assert.equal(manifest.selection.literal_game_sha256, expectedLiteralDigest);
  assert.equal(manifest.selection.observed_quotient_forms, 193);

  const forms = fiber.items;
  assert.equal(forms.length, 193);
  assert.equal(new Set(forms.map((item) => `${item.g}:${item.m}`)).size, 193);
  assert.equal(new Set(forms.map((item) => item.q)).size, 193);
  assert.equal(new Set(forms.map((item) => item.c)).size, 193);
  assert.equal(new Set(forms.map((item) => item.e)).size, 193);
  assert.equal(new Set(forms.map((item) => item.i)).size, 193);
  assert.deepEqual(
    [...new Set(forms.map((item) => item.a))].sort((left, right) => left - right),
    expectedArcColumns,
  );
  assert.ok(forms.every((item) => item.b === 3));
  assert.ok(forms.every((item) => item.n === 20));
  assert.ok(forms.every((item) => item.p.length === 2));
  assert.deepEqual(fiber.measurements.graph_arc_range, [17, 27]);
  assert.equal(fiber.measurements.observed_distinct_adjacency_colorings, 193);
  assert.equal(fiber.claim_boundary.aesthetic_preference, "not_measured");
  assert.equal(fiber.claim_boundary.total_mathematical_fiber_size, "not_estimated");
  assert.equal(
    fiber.literal_game_dag.nodes[fiber.literal_game_dag.root].d,
    expectedLiteralDigest,
  );
});

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("hero-contract", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("the 193-form hero exposes evidence, columns, and reachable controls", async () => {
  const [experienceSource, globalCss, response] = await Promise.all([
    readFile(new URL("../app/experience.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    render(),
  ]);
  const html = (await response.text()).replaceAll("<!-- -->", "");

  assert.equal(response.status, 200);
  assert.match(html, /data-fixed-fiber-hero=["']193["']/i);
  assert.match(html, /193[^<]{0,80}(graph )?forms/i);
  assert.match(html, /(?:value[^<]{0,30}1\/2|1\/2[^<]{0,30}value)/i);
  assert.match(
    html,
    new RegExp(expectedLiteralDigest),
    "the hero must disclose the shared complete-game identity",
  );

  for (const arcCount of expectedArcColumns) {
    assert.match(
      html,
      new RegExp(`data-arc-column=["']${arcCount}["']`, "i"),
      `the hero must render an explicit ${arcCount}-arc column`,
    );
  }

  const heroCanvas = experienceSource.match(
    /<canvas\b(?=[^>]*data-fiber-hero-canvas)[^>]*>/i,
  )?.[0];
  assert.ok(heroCanvas, "the focused hero needs a stable canvas hook");
  assert.match(heroCanvas, /tabIndex=\{0\}/);
  assert.match(heroCanvas, /aria-describedby=/);
  assert.match(heroCanvas, /onKeyDown=/);
  assert.match(heroCanvas, /onClick=|onPointerDown=|onPointerUp=/);
  assert.match(experienceSource, /ArrowLeft/);
  assert.match(experienceSource, /ArrowRight/);
  assert.match(experienceSource, /Escape/);
  assert.match(experienceSource, /data-fiber-(?:previous|prev)/i);
  assert.match(experienceSource, /data-fiber-next/i);
  assert.match(experienceSource, /data-fiber-neighborhood=["']9["']/i);
  assert.match(experienceSource, /const neighborhoodSize = 9/);
  assert.match(experienceSource, /Nine forms near the selection/);
  assert.match(experienceSource, /data-fiber-specimen/i);
  assert.match(experienceSource, /const rows = 11/);
  assert.match(experienceSource, /scroller\.scrollTo/);
  assert.match(
    experienceSource,
    /selected\.item\.q === reference\.item\.q \? "same" : "different"/,
  );
  assert.doesNotMatch(
    experienceSource,
    /className="fiber-inspector"\s+aria-live=/,
    "the complete inspector must not be a live region",
  );

  assert.doesNotMatch(
    experienceSource,
    /data-plot-overlay|plot-overlay/i,
    "the focused plot must not be covered by an explanatory card",
  );
  assert.match(experienceSource, /data-secondary-corpus-view/i);
  assert.match(experienceSource, /graph in\s+this class/i);
  assert.match(experienceSource, /column containing the median form/i);
  assert.match(experienceSource, /similar silhouettes/i);
  assert.match(experienceSource, /<details className="further-example"/i);
  assert.match(experienceSource, /log(?:arithmic)?/i);
  assert.match(experienceSource, /jitter/i);

  assert.match(globalCss, /@media\s*\(max-width:\s*680px\)/i);
  assert.match(globalCss, /@media\s*\(prefers-reduced-motion:\s*reduce\)/i);
  assert.match(globalCss, /touch-action:\s*manipulation/i);
  assert.match(globalCss, /min-(?:height|block-size):\s*(?:44|46|48|52|56|58)px/i);
  assert.match(
    globalCss,
    /\.fiber-intro h1\s*\{[\s\S]*?font-size:\s*clamp\(2\.15rem,\s*4\.4vw,\s*4\.25rem\)/i,
  );
  assert.match(
    globalCss,
    /\.atlas-intro h1\s*\{[^}]*font-size:\s*clamp\(1\.7rem,\s*2\.65vw,\s*2\.65rem\)/i,
  );
  assert.doesNotMatch(
    experienceSource,
    /—|\b(?:delve|tapestry|game-changer|seamless|remarkable|groundbreaking)\b/i,
  );
});

test("the full-corpus fallback remains compressed and canvas-bounded", async () => {
  const [experienceSource, compressedAtlas] = await Promise.all([
    readFile(new URL("../app/experience.tsx", import.meta.url), "utf8"),
    stat(new URL("../public/evidence/fixed-value-atlas.json.gz", import.meta.url)),
  ]);

  assert.ok(
    compressedAtlas.size < 2.5 * 1024 * 1024,
    `compressed atlas grew to ${compressedAtlas.size} bytes`,
  );
  assert.match(experienceSource, /ResizeObserver/);
  assert.match(experienceSource, /requestAnimationFrame/);
  assert.match(experienceSource, /Math\.min\(window\.devicePixelRatio\s*\|\|\s*1,\s*2\)/);
  assert.match(experienceSource, /fixed-value-atlas\.json\.gz/);
});
