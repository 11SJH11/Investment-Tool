import test from 'node:test';
import assert from 'node:assert/strict';
import {campaignDisplayStatus,campaignActions} from '../src/features/strategy-lab/campaignView.js';

test('Failed persisted evidence overrides a misleading terminal label without mutating controls',()=>{
 const report={campaign:{status:'DEVELOPMENT_COMPLETE'},progress:{outcome:'FAILED'}};
 assert.equal(campaignDisplayStatus(report),'FAILED');
 assert.equal(report.campaign.status,'DEVELOPMENT_COMPLETE');
 assert.deepEqual(campaignActions(report.campaign.status),[]);
});
test('Mixed outcome and old-server fallback remain explicit',()=>{
 assert.equal(campaignDisplayStatus({progress:{outcome:'COMPLETED_WITH_ERRORS'}}),'COMPLETED_WITH_ERRORS');
 assert.equal(campaignDisplayStatus({campaign:{status:'ACTIVE'}}),'ACTIVE');
 assert.equal(campaignDisplayStatus(null),'Unavailable');
});
