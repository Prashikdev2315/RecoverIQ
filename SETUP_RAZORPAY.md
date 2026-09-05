# Setup Guide: Razorpay Integration

## Step 1: Create Razorpay Test Account

1. Go to https://dashboard.razorpay.com/signup
2. Sign up for a free account
3. Verify your email
4. Switch to **Test Mode** (toggle in the top-left corner)

## Step 2: Get API Keys

1. Navigate to **Settings** → **API Keys**
2. Click **Generate Test Key** if you don't have one
3. Copy your:
   - **Key ID** (starts with `rzp_test_`)
   - **Key Secret** (click "Show" to reveal)
4. Add these to your `.env` file:
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxx
   RAZORPAY_KEY_SECRET=your_secret_here
   ```

## Step 3: Setup Webhook

1. In Razorpay Dashboard, go to **Settings** → **Webhooks**
2. Click **Create New Webhook**
3. Configure:
   - **Webhook URL**: `https://your-ngrok-url.ngrok.io/webhooks/razorpay`
   - **Alert Email**: Your email
   - **Active Events**: Select these three:
     - ✓ `payment.failed`
     - ✓ `subscription.charged.failed`
     - ✓ `subscription.pending`
   - **Secret**: Generate and copy this (it's shown only once!)
4. Save the webhook
5. Add the secret to your `.env`:
   ```
   RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here
   ```

## Step 4: Test the Integration

### Option A: Trigger a Test Event from Razorpay Dashboard

1. In Razorpay Dashboard, go to **Webhooks**
2. Click on your webhook
3. Go to **Test Webhook** tab
4. Select `payment.failed` event
5. Click **Send Test Webhook**
6. Check your server logs - you should see: `✓ Processed payment.failed event`

### Option B: Create a Real Test Payment

1. Use Razorpay's test payment link API or create a payment manually
2. Use test card numbers that trigger failures:
   - **Card**: `4111 1111 1111 1111`
   - **CVV**: `123`
   - **Expiry**: `12/25`
   - To simulate failure: Use amount `100` (₹1.00) - payments under ₹1 fail in test mode

## Step 5: Verify Webhook is Working

Check your FastAPI server logs. You should see:

```
✓ Processed payment.failed event: pay_xxxxxxxxxxxxx
```

Or check the webhook logs in Razorpay Dashboard - successful deliveries show **200 OK**.

## Test Card Numbers (Razorpay Test Mode)

| Card Number | Behavior |
|---|---|
| 4111 1111 1111 1111 | Success (use with amount > 100 paise) |
| 4000 0000 0000 0002 | Declined |
| 4000 0000 0000 0010 | Insufficient funds |
| 5105 1051 0510 5100 | Success (Mastercard) |

## Troubleshooting

### Webhook not receiving events?

1. **Check ngrok is running**: `ngrok http 8000`
2. **Check server is running**: `python backend/main.py`
3. **Verify URL in Razorpay**: Must be the HTTPS ngrok URL
4. **Check signature secret**: Must match exactly in `.env` and Razorpay dashboard

### Signature verification failing?

1. Ensure `RAZORPAY_WEBHOOK_SECRET` is set correctly in `.env`
2. Restart your FastAPI server after changing `.env`
3. Check webhook logs in Razorpay Dashboard for error details

### Database connection errors?

1. Verify PostgreSQL is running
2. Check `DATABASE_URL` in `.env` matches your database credentials
3. Ensure database exists: `psql -l | grep revenue_recovery`
4. Verify schema is loaded: `psql revenue_recovery -c "\dt"`

## Security Notes

- ✓ Never commit your `.env` file (it's in `.gitignore`)
- ✓ Only use test mode keys for development
- ✓ Webhook signature verification is mandatory - the code enforces this
- ✓ For production, rotate secrets regularly and use a secrets manager
