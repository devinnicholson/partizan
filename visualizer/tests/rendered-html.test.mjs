import assert from "node:assert/strict";
import { gunzipSync } from "node:zlib";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
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

test("server-renders the finished Partizan experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  const normalizedHtml = html.replaceAll("<!-- -->", "");
  assert.match(html, /<title>Partizan \| 193 Graph Forms Sharing One Complete Game<\/title>/i);
  assert.match(html, /Certified equivalence class/);
  assert.match(normalizedHtml, /193 graph forms share one complete game\./i);
  assert.match(normalizedHtml, /graph in this class/i);
  assert.match(normalizedHtml, /column containing the median form/i);
  assert.match(html, /Corpus overview/);
  assert.match(normalizedHtml, /similar silhouettes/i);
  assert.match(normalizedHtml, /21,697 certified graph forms at three exact values\./);
  assert.match(html, /Graph form/);
  assert.match(html, /Complete game/);
  assert.match(html, /Exact value/);
  assert.match(html, /Group by complete game/);
  assert.match(normalizedHtml, /7,555[\s\S]*?graph forms/);
  assert.match(normalizedHtml, /6,386[\s\S]*?complete games/);
  assert.match(html, /Three graph forms, two complete games, value 0/);
  assert.match(html, /<details[^>]*class="further-example"/i);
  assert.doesNotMatch(html, /<details[^>]*class="further-example"[^>]*\sopen(?:\s|>)/i);
  assert.match(html, /Show A, B, and C/);
  assert.match(html, /Copy verification record/);
  assert.match(html, /og-progressive\.png/);
  assert.match(normalizedHtml, /73,728/);
  assert.match(normalizedHtml, /21,697/);
  assert.match(normalizedHtml, /16,120/);
  assert.match(normalizedHtml, /corruption families rejected/);
  assert.match(html, /These counts describe the observed sample\./);
  assert.match(html, /Stiller used computation to locate an endgame kernel/);
  assert.match(html, /Elkies recomposed it as a chess study/);
  assert.doesNotMatch(html, /linear-gradient|radial-gradient/i);
  assert.doesNotMatch(html, /Select form/i);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("ships checked evidence and removes the starter preview", async () => {
  const [
    evidence,
    historicalEvidence,
    motifEvidence,
    atlasEvidence,
    atlasManifestEvidence,
    repertoireEvidence,
    policyResultEvidence,
    globalCss,
    packageJson,
  ] = await Promise.all([
    readFile(new URL("../public/evidence/crossing.json", import.meta.url), "utf8"),
    readFile(
      new URL("../public/evidence/elkies-study.json", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL("../public/evidence/fixed-value-motif.json", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL("../public/evidence/fixed-value-atlas.json.gz", import.meta.url),
    ),
    readFile(
      new URL("../public/evidence/fixed-value-atlas.manifest.json", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL("../public/evidence/repertoire-browser.json", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL("../public/evidence/site-policy-result.json", import.meta.url),
      "utf8",
    ),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);
  const parsed = JSON.parse(evidence);
  const historical = JSON.parse(historicalEvidence);
  const motif = JSON.parse(motifEvidence);
  const atlas = JSON.parse(gunzipSync(atlasEvidence).toString("utf8"));
  const atlasManifest = JSON.parse(atlasManifestEvidence);
  const repertoire = JSON.parse(repertoireEvidence);
  const policyResult = JSON.parse(policyResultEvidence);

  assert.equal(parsed.schema_version, "partizan.visual_crossing.v0.1");
  assert.deepEqual(
    parsed.realizations.map((item) => item.statistics.literal_game_nodes),
    [19, 11],
  );
  assert.deepEqual(
    parsed.realizations.map((item) => item.witness.move),
    ["Qg1-g7", "Qg6-g7"],
  );
  assert.equal(parsed.comparison.equal_to_each_other, true);
  assert.equal(
    historical.schema_version,
    "partizan.historical_chess_witness.v0.1",
  );
  assert.equal(historical.scope.legal_replay, "machine_verified");
  assert.equal(historical.scope.cgt_value, "not_asserted");
  assert.equal(historical.witness.move_count, 13);
  assert.equal(historical.witness.frames.length, 14);
  assert.equal(historical.witness.frames.at(-1).move_san, "Qfg8");
  assert.equal(
    historical.witness.frames.at(-1).fen,
    "6QK/6Q1/2q5/8/8/8/8/1q5k b - - 3 7",
  );
  assert.equal(motif.schema_version, "partizan.fixed_value_linked_motif.v1");
  assert.equal(motif.comparison.exact_value, "0");
  assert.notEqual(
    motif.positions[0].literal_game_sha256,
    motif.positions[1].literal_game_sha256,
  );
  assert.equal(
    motif.positions[1].literal_game_sha256,
    motif.positions[2].literal_game_sha256,
  );
  assert.equal(motif.atlas.quotient_unique_representatives, 21697);
  assert.equal(atlas.schema_version, "partizan.fixed_value_atlas.v1");
  assert.equal(
    atlasManifest.schema_version,
    "partizan.fixed_value_atlas.publication.v1",
  );
  assert.equal(atlasManifest.artifact.file, "fixed-value-atlas.json.gz");
  assert.equal(atlasManifest.atlas_sha256, atlas.atlas_sha256);
  assert.deepEqual(atlas.counts, {
    exact_values: 3,
    literal_games: 16120,
    quotient_forms: 21697,
  });
  assert.equal(atlas.items.length, 21697);
  assert.equal(atlas.groups.length, 16120);
  assert.deepEqual(
    atlas.targets.map((target) => target.quotient_forms),
    [7555, 7132, 7010],
  );
  assert.deepEqual(
    atlas.targets.map((target) => target.literal_games),
    [6386, 5352, 4382],
  );
  assert.equal(
    atlas.source.representative_set_sha256,
    "54488c811edd8a09155864fd1af3c469c7daba334c62788a86882e0e9c404a02",
  );
  assert.equal(atlas.source.independent_replay, true);
  assert.equal(atlas.source.proposal_count, 73728);
  assert.equal(atlas.source.negative_test_families_rejected, 15);
  assert.match(atlas.source.completion_file_sha256, /^[0-9a-f]{64}$/);
  assert.match(atlas.source.negative_tests_file_sha256, /^[0-9a-f]{64}$/);
  assert.equal(atlas.groups[atlas.items[atlas.motif.A].l].c, 32);
  assert.equal(atlas.groups[atlas.items[atlas.motif.B].l].c, 54);
  assert.equal(atlas.items[atlas.motif.B].l, atlas.items[atlas.motif.C].l);
  assert.notEqual(atlas.items[atlas.motif.A].l, atlas.items[atlas.motif.B].l);
  assert.ok(atlas.items.every((item) => item.p.length === 6));
  assert.ok(atlas.groups.every((group) => group.p.length === 2));
  assert.equal(
    repertoire.schema_version,
    "partizan.repertoire_browser.v0.1",
  );
  assert.equal(repertoire.study.policy.status, "verified");
  assert.equal(
    repertoire.study.result_contract.schema_version,
    "partizan.policy_result.v0.1",
  );
  assert.deepEqual(
    repertoire.results.map((result) => result.target),
    ["0", "*", "1/2"],
  );
  assert.deepEqual(
    repertoire.results.map((result) => result.quotient_unique_representatives),
    motif.atlas.targets.map((target) => target.quotients),
  );
  assert.deepEqual(
    repertoire.results.map((result) => result.literal_game_digests),
    motif.atlas.targets.map((target) => target.literal_games),
  );
  assert.ok(
    repertoire.results.every((result) => result.budget.unit === "raw_proposal"),
  );
  assert.equal(
    repertoire.results.reduce((total, result) => total + result.budget.count, 0),
    motif.run.proposal_count,
  );
  assert.equal(
    repertoire.bindings.completion_sha256,
    motif.completion_sha256,
  );
  assert.match(repertoire.bindings.manifest_file_sha256, /^[0-9a-f]{64}$/);
  assert.equal(repertoire.representative_provenance.length, 3);
  assert.deepEqual(
    repertoire.representative_provenance.map((record) => record.candidate_sha256),
    motif.positions.map((position) => position.candidate_sha256),
  );
  assert.deepEqual(
    repertoire.representative_provenance.map((record) => record.global_event_index),
    motif.positions.map((position) => position.first_global_event_index),
  );
  assert.equal(repertoire.claim_boundary.aesthetic_ranking, "not_measured");
  assert.equal(repertoire.claim_boundary.policy_optimality, "not_tested");
  assert.equal(
    policyResult.schema_version,
    "partizan.digraph_order7_neural_policy_promotion.v1.site_policy_result",
  );
  assert.equal(policyResult.result, "NO_GO");
  assert.equal(policyResult.learned_advantage_claim, null);
  assert.equal(policyResult.budget.total_calls, 147456);
  assert.equal(
    policyResult.observed_analysis.total_discoveries.neural_toggle_one_ranker,
    68232,
  );
  assert.equal(
    policyResult.observed_analysis.total_discoveries.structural_toggle_one_random,
    43301,
  );
  assert.equal(
    policyResult.diversity.literal_game_digest_counts.neural_toggle_one_ranker,
    11083,
  );
  assert.equal(
    policyResult.diversity.literal_game_digest_counts.structural_toggle_one_random,
    27990,
  );
  assert.equal(
    policyResult.scientific_gates.minimum_literal_digest_ratio_to_control,
    false,
  );
  assert.equal(policyResult.independent_replay, true);
  assert.equal(policyResult.corruption_families_rejected, 20);
  assert.doesNotMatch(globalCss, /linear-gradient|radial-gradient/i);
  assert.match(globalCss, /--paper:\s*#090908/i);
  assert.match(globalCss, /--stage:\s*#090908/i);
  assert.match(globalCss, /--paper-accent:\s*#e96f58/i);
  assert.match(globalCss, /min-height:\s*44px/i);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  await access(new URL("../public/og.png", import.meta.url));
  await assert.rejects(access(new URL("../app/_sites-preview", root)));
});
