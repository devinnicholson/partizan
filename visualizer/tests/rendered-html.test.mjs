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
  assert.match(html, /<title>Partizan — One Value, Three Forms<\/title>/i);
  assert.match(html, /One value\./);
  assert.match(html, /Three forms\./);
  assert.match(html, /A machine found the kernel\./);
  assert.match(html, /Elkies composed the encounter\./);
  assert.match(html, /Play 13 plies/);
  assert.match(html, /Qfg8/);
  assert.match(html, /legal replay machine-verified/);
  assert.match(html, /CGT value unasserted here/);
  assert.match(html, /Correctness is the entrance\./);
  assert.match(html, /The search continues inside\./);
  assert.match(html, /og\.png/);
  assert.match(html, /remove 2→3/i);
  assert.match(html, /add 6→0/i);
  assert.match(html, /literal-game crossing/);
  assert.match(html, /embodiment only/);
  assert.match(html, /21,697 certified forms/);
  assert.match(html, /Enter the fiber/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("ships checked evidence and removes the starter preview", async () => {
  const [evidence, historicalEvidence, motifEvidence, packageJson] = await Promise.all([
    readFile(new URL("../public/evidence/crossing.json", import.meta.url), "utf8"),
    readFile(
      new URL("../public/evidence/elkies-study.json", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL("../public/evidence/fixed-value-motif.json", import.meta.url),
      "utf8",
    ),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);
  const parsed = JSON.parse(evidence);
  const historical = JSON.parse(historicalEvidence);
  const motif = JSON.parse(motifEvidence);

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
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  await access(new URL("../public/og.png", import.meta.url));
  await assert.rejects(access(new URL("../app/_sites-preview", root)));
});
