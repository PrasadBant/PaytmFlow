import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

const outputDir = path.resolve('C:/Users/sri charan uppuluri/.gemini/antigravity-ide/brain/564cba4e-3a33-4ece-923c-c09aecad4465/visual-qa');
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 375, height: 812 },
];

const JOURNEY_ID = '11111111-1111-1111-1111-111111111111';

const EVIDENCE_SALARY_SLIP = {
  evidence_id: '22222222-2222-2222-2222-222222222222',
  filename: 'payslip_august_2026.pdf',
  uploaded_at: '2026-09-12T10:05:00Z',
  size_bytes: 1428500,
  interpretation: {
    verified: true,
    confidence: 0.96,
    detected: [
      { key: 'monthly_income', label: 'Net Monthly Salary', display_value: '₹85,000' },
    ],
    summary: 'Verified August 2026 salary slip confirming net in-hand credit of ₹85,000.',
    conflicts: [],
  },
  proposed_action_id: 'UPLOAD_INCOME_PROOF',
  consequence_preview: {
    newly_satisfied: [{ key: 'monthly_income', label: 'Verified Monthly Income' }],
    newly_unlocked: [{ action_id: 'UPLOAD_BANK_STATEMENT', title: 'Upload Bank Statement' }],
    still_blocked: [{ key: 'bank_statement', label: 'Bank Statement' }],
    predicted_progress: { completed: 4, total: 7 },
  },
  diff_preview: {
    fields_changed: [],
    actions_unlocked: [],
    actions_removed: [],
    readiness_transition: null,
  },
  requires_review: false,
};

const ACTION_RESPONSE_V2 = {
  journey: {
    journey_id: JOURNEY_ID,
    session_id: '00000000-0000-0000-0000-000000000001',
    journey_type: 'LENDING',
    version_number: 2,
    snapshot_id: 'bbbbbbbb-2222-2222-2222-222222222222',
    readiness: 'NOT_READY',
    status: 'IN_PROGRESS',
    progress: { completed: 4, pending: 2, blockers: 1, total: 7 },
    fields: [
      { key: 'loan_amount', label: 'Loan Amount', status: 'SATISFIED', display_value: '₹5,00,000', mandatory: true },
      { key: 'monthly_income', label: 'Monthly Income', status: 'SATISFIED', display_value: '₹85,000', mandatory: true },
      { key: 'bank_statement', label: 'Salary Bank Statement', status: 'BLOCKED', explanation: 'Upload 6 months statement.', resolve_action_id: 'UPLOAD_BANK_STATEMENT', mandatory: true },
      { key: 'pan_card', label: 'PAN Card Verification', status: 'BLOCKED', resolve_action_id: 'VERIFY_PAN', mandatory: true },
    ],
    display: { title: 'Personal Loan', summary: '₹5,00,000 · Home Renovation' },
    updated_at: '2026-09-12T10:10:00Z',
  },
  diff: {
    from_version: 1,
    to_version: 2,
    fields_changed: [
      { key: 'monthly_income', label: 'Monthly Income', from_status: 'BLOCKED', to_status: 'SATISFIED', display_value: '₹85,000', cause: 'ACTION:UPLOAD_INCOME_PROOF' },
    ],
    actions_unlocked: ['UPLOAD_BANK_STATEMENT'],
    actions_removed: ['UPLOAD_INCOME_PROOF'],
    readiness: { from: 'NOT_READY', to: 'NOT_READY' },
    progress: { from: { completed: 3, pending: 3, blockers: 1, total: 7 }, to: { completed: 4, pending: 2, blockers: 1, total: 7 } },
  },
  next_recommendation: {
    snapshot_id: 'bbbbbbbb-2222-2222-2222-222222222222',
    readiness: 'NOT_READY',
    recommendation: { action_id: 'UPLOAD_BANK_STATEMENT', title: 'Upload Bank Statement', kind: 'EVIDENCE', why: 'Required to verify salary credits.', unlocks: ['FINAL_DISBURSEMENT'] },
    alternatives: [],
    minimum_path_length: 1,
  },
};

async function gotoWithState(page, urlPath, userState) {
  await page.goto(urlPath);
  await page.waitForSelector('#root > *', { timeout: 10000 });
  await page.evaluate(
    ([p, s]) => {
      const existing = window.history.state;
      const idx = (existing && typeof existing.idx === 'number') ? existing.idx : 0;
      const key = (existing && typeof existing.key === 'string') ? existing.key : 'default';
      window.history.replaceState({ usr: s, idx, key }, '', p);
    },
    [urlPath, userState]
  );
  await page.evaluate((p) => {
    window.history.pushState(window.history.state, '', p);
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  }, urlPath);
  await page.waitForTimeout(400);
}

async function run() {
  const browser = await chromium.launch({ headless: true });

  for (const vp of viewports) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();

    // 1. Screen 1: Home
    await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen01_home_${vp.name}.png`), fullPage: true });

    // 2. Screen 2: Journey Selection
    await page.goto('http://localhost:5173/start', { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen02_selection_${vp.name}.png`), fullPage: true });

    // 3. Screen 3: Goal & Basic Info Form
    await page.goto('http://localhost:5173/start/lending', { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen03_goal_${vp.name}.png`), fullPage: true });

    // 4. Screen 4: Current Status
    await page.goto(`http://localhost:5173/j/${JOURNEY_ID}`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen04_status_${vp.name}.png`), fullPage: true });

    // 5. Screen 5: Recommendation
    await page.goto(`http://localhost:5173/j/${JOURNEY_ID}/next`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen05_recommendation_${vp.name}.png`), fullPage: true });

    // 6. Screen 6: Upload Evidence
    await page.goto(`http://localhost:5173/j/${JOURNEY_ID}/act/UPLOAD_INCOME_PROOF`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen06_upload_${vp.name}.png`), fullPage: true });

    // 7. Screen 7: AI Analysis
    await gotoWithState(page, `http://localhost:5173/j/${JOURNEY_ID}/analysis`, {
      evidenceResponse: EVIDENCE_SALARY_SLIP,
      journeyId: JOURNEY_ID,
      actionId: 'UPLOAD_INCOME_PROOF',
      snapshotId: 'aaaaaaaa-1111-1111-1111-111111111111',
    });
    await page.screenshot({ path: path.join(outputDir, `screen07_analysis_${vp.name}.png`), fullPage: true });

    // 8. Screen 8: Updated Status
    await gotoWithState(page, `http://localhost:5173/j/${JOURNEY_ID}/updated`, {
      actionResponse: ACTION_RESPONSE_V2,
      journeyId: JOURNEY_ID,
    });
    await page.screenshot({ path: path.join(outputDir, `screen08_updated_${vp.name}.png`), fullPage: true });

    // 9. Screen 9: Complete Journey (Guarded / Not Ready)
    await page.goto(`http://localhost:5173/j/${JOURNEY_ID}/complete`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen09_complete_guarded_${vp.name}.png`), fullPage: true });

    // 10. Screen 10: My Journeys
    await page.goto('http://localhost:5173/my-journeys', { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen10_my_journeys_${vp.name}.png`), fullPage: true });

    // Edge State 1: Empty Journeys List
    await page.goto('http://localhost:5173/my-journeys?scenario=empty', { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen10_empty_${vp.name}.png`), fullPage: true });

    // Edge State 2: Dead End Status
    await page.goto(`http://localhost:5173/j/${JOURNEY_ID}?scenario=deadend`, { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(outputDir, `screen04_deadend_${vp.name}.png`), fullPage: true });

    // Mobile Drawer
    if (vp.name === 'mobile') {
      await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
      const menuBtn = page.getByRole('button', { name: /toggle navigation menu|open menu/i });
      if (await menuBtn.isVisible()) {
        await menuBtn.click();
        await page.waitForTimeout(300);
        await page.screenshot({ path: path.join(outputDir, `mobile_drawer_open.png`) });
      }
    }

    await context.close();
  }

  await browser.close();
  console.log('Comprehensive visual QA screenshots captured successfully.');
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
