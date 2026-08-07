import assert from "node:assert/strict";
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
  assert.match(html, /<title>Partizan \| Different Forms, One Value<\/title>/i);
  assert.match(html, /A certified crossing/);
  assert.match(html, /What remains when correctness is fixed\?/);
  assert.match(normalizedHtml, /B and C/);
  assert.match(normalizedHtml, /Form B/);
  assert.match(normalizedHtml, /Form C/);
  assert.match(html, /Isolate the change/);
  assert.match(html, /Crossing stages/);
  assert.match(html, /One complete game\./);
  assert.match(normalizedHtml, /q\(B\) ≠ q\(C\)/);
  assert.match(normalizedHtml, /ℓ\(B\) = ℓ\(C\)/);
  assert.match(normalizedHtml, /v\(B\) = v\(C\) = 0/);
  assert.match(html, /Technical evidence/);
  assert.match(html, /Copy evidence JSON/);
  assert.match(html, /Download evidence JSON/);
  assert.match(html, /og-v2\.png/);
  assert.match(normalizedHtml, /73,728/);
  assert.match(normalizedHtml, /21,697/);
  assert.match(normalizedHtml, /8,111/);
  assert.match(html, /Mathematics can identify two objects/);
  assert.match(html, /Form C adds/);
  assert.match(html, /Lewis Stiller found an endgame kernel\./);
  assert.match(html, /Noam Elkies composed a study around it\./);
  assert.doesNotMatch(html, /linear-gradient|radial-gradient/i);
  assert.doesNotMatch(html, /Select form/i);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("ships checked evidence and removes the starter preview", async () => {
  const [
    evidence,
    historicalEvidence,
    motifEvidence,
    repertoireEvidence,
    policyResultEvidence,
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
      new URL("../public/evidence/repertoire-browser.json", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL("../public/evidence/site-policy-result.json", import.meta.url),
      "utf8",
    ),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);
  const parsed = JSON.parse(evidence);
  const historical = JSON.parse(historicalEvidence);
  const motif = JSON.parse(motifEvidence);
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
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  await access(new URL("../public/og-v2.png", import.meta.url));
  await assert.rejects(access(new URL("../app/_sites-preview", root)));
});
