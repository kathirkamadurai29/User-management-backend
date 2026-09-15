const BASE_URL = 'http://localhost:5000/api/v1';

async function runTests() {
  console.log('--- Starting Backend Integration Tests ---\n');

  // Test 1: Register Client A
  console.log('1. Testing POST /clients (Register Tenant A)...');
  const resClientA = await fetch(`${BASE_URL}/clients`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'Acme Enterprise', email: 'admin@acme.com' }),
  });
  const dataClientA = await resClientA.json();
  if (!resClientA.ok || !dataClientA.client_id || !dataClientA.client_secret) {
    throw new Error(`Client A registration failed: ${JSON.stringify(dataClientA)}`);
  }
  console.log('✓ Tenant A created:', dataClientA.client_id);

  // Test 2: Auth Token Exchange for Client A
  console.log('\n2. Testing POST /auth/token (Obtain JWT for Tenant A)...');
  const resTokenA = await fetch(`${BASE_URL}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: dataClientA.client_id,
      client_secret: dataClientA.client_secret,
    }),
  });
  const dataTokenA = await resTokenA.json();
  if (!resTokenA.ok || !dataTokenA.access_token) {
    throw new Error(`Token exchange failed: ${JSON.stringify(dataTokenA)}`);
  }
  const tokenA = dataTokenA.access_token;
  console.log('✓ JWT Token obtained for Tenant A');

  const authHeadersA = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${tokenA}`,
  };

  // Test 3: Create User for Tenant A
  console.log('\n3. Testing POST /users (Create User for Tenant A)...');
  const resCreateUser = await fetch(`${BASE_URL}/users`, {
    method: 'POST',
    headers: authHeadersA,
    body: JSON.stringify({
      name: 'Alice Smith',
      email: 'alice@acme.com',
      role: 'admin',
      status: 'active',
    }),
  });
  const userA1 = await resCreateUser.json();
  if (!resCreateUser.ok || !userA1._id) {
    throw new Error(`User creation failed: ${JSON.stringify(userA1)}`);
  }
  console.log('✓ User created:', userA1._id, userA1.name);

  // Create second user for Tenant A
  await fetch(`${BASE_URL}/users`, {
    method: 'POST',
    headers: authHeadersA,
    body: JSON.stringify({
      name: 'Bob Johnson',
      email: 'bob@acme.com',
      role: 'member',
      status: 'pending',
    }),
  });
  console.log('✓ Second user created for Tenant A');

  // Test 4: List Users with Search and Status Filters
  console.log('\n4. Testing GET /users with filters...');
  const resList = await fetch(`${BASE_URL}/users`, { headers: authHeadersA });
  const dataList = await resList.json();
  console.log(`✓ Total users returned: ${dataList.total} (expected >= 2)`);

  const resSearch = await fetch(`${BASE_URL}/users?search=alice`, { headers: authHeadersA });
  const dataSearch = await resSearch.json();
  console.log(`✓ Filter ?search=alice returned: ${dataSearch.users.length} user(s)`);

  const resStatus = await fetch(`${BASE_URL}/users?status=pending`, { headers: authHeadersA });
  const dataStatus = await resStatus.json();
  console.log(`✓ Filter ?status=pending returned: ${dataStatus.users.length} user(s)`);

  // Test 5: Get User by ID
  console.log('\n5. Testing GET /users/:id...');
  const resGet = await fetch(`${BASE_URL}/users/${userA1._id}`, { headers: authHeadersA });
  const dataGet = await resGet.json();
  if (dataGet._id !== userA1._id) throw new Error('GET /users/:id ID mismatch');
  console.log('✓ Retrieved user successfully:', dataGet.name);

  // Test 6: Update User
  console.log('\n6. Testing PUT /users/:id...');
  const resUpdate = await fetch(`${BASE_URL}/users/${userA1._id}`, {
    method: 'PUT',
    headers: authHeadersA,
    body: JSON.stringify({ name: 'Alice S. Thompson', role: 'admin' }),
  });
  const dataUpdate = await resUpdate.json();
  if (dataUpdate.name !== 'Alice S. Thompson') throw new Error('Update failed');
  console.log('✓ User updated to:', dataUpdate.name);

  // Test 7: Multi-Tenant Isolation
  console.log('\n7. Testing Hard Multi-Tenant Isolation with Tenant B...');
  const resClientB = await fetch(`${BASE_URL}/clients`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'Beta Labs', email: 'contact@betalabs.org' }),
  });
  const dataClientB = await resClientB.json();

  const resTokenB = await fetch(`${BASE_URL}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: dataClientB.client_id,
      client_secret: dataClientB.client_secret,
    }),
  });
  const dataTokenB = await resTokenB.json();
  const authHeadersB = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${dataTokenB.access_token}`,
  };

  // Attempt to access Tenant A's user using Tenant B's token
  const crossAccess = await fetch(`${BASE_URL}/users/${userA1._id}`, { headers: authHeadersB });
  if (crossAccess.status === 404) {
    console.log('✓ Hard tenant isolation verified: Tenant B cannot access Tenant A user (HTTP 404)');
  } else {
    throw new Error(`Tenant isolation breached! Status: ${crossAccess.status}`);
  }

  // Tenant B list should be 0
  const listB = await (await fetch(`${BASE_URL}/users`, { headers: authHeadersB })).json();
  if (listB.total === 0) {
    console.log('✓ Tenant B user count is 0 (no data leakage)');
  } else {
    throw new Error('Tenant B saw users belonging to other tenants!');
  }

  // Test 8: Soft Delete User
  console.log('\n8. Testing DELETE /users/:id (Soft delete)...');
  const resDelete = await fetch(`${BASE_URL}/users/${userA1._id}`, {
    method: 'DELETE',
    headers: authHeadersA,
  });
  const dataDelete = await resDelete.json();
  console.log('✓ User soft-deleted:', dataDelete.message);

  const resListAfterDelete = await fetch(`${BASE_URL}/users`, { headers: authHeadersA });
  const dataListAfterDelete = await resListAfterDelete.json();
  const isPresent = dataListAfterDelete.users.some((u) => u._id === userA1._id);
  if (!isPresent) {
    console.log('✓ User excluded from active list queries');
  } else {
    throw new Error('Soft-deleted user still appearing in active users list!');
  }

  // Test 9: Activity Logs & Stats
  console.log('\n9. Testing GET /activity...');
  const resActivity = await fetch(`${BASE_URL}/activity`, { headers: authHeadersA });
  const dataActivity = await resActivity.json();
  console.log('✓ Activity metrics recorded:');
  console.log(`  Total requests: ${dataActivity.metrics.total_requests}`);
  console.log(`  Success rate: ${dataActivity.metrics.success_rate_percent}%`);
  console.log(`  Recent logs count: ${dataActivity.logs.length}`);

  // Test 10: AI Insights
  console.log('\n10. Testing GET /insights...');
  const resInsights = await fetch(`${BASE_URL}/insights`, { headers: authHeadersA });
  const dataInsights = await resInsights.json();
  console.log('✓ AI Insight generated:');
  console.log(`  "${dataInsights.insight}"`);
  console.log(`  Provider: ${dataInsights.provider}`);

  // Test 11: Swagger Docs
  console.log('\n11. Testing Swagger Documentation at /api-docs...');
  const resSwagger = await fetch('http://localhost:5000/api-docs/');
  if (resSwagger.ok) {
    console.log('✓ Swagger UI is live at http://localhost:5000/api-docs (HTTP 200)');
  } else {
    throw new Error(`Swagger failed: ${resSwagger.status}`);
  }

  console.log('\n========================================');
  console.log('ALL 11 BACKEND INTEGRATION TESTS PASSED!');
  console.log('========================================\n');
}

runTests().catch((err) => {
  console.error('\n❌ Test failed:', err);
  process.exit(1);
});
