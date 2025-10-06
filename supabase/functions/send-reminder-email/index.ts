import { serve } from "https://deno.land/std@0.168.0/http/server.ts"

// Get the Resend API key from the environment variables
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY")
const FROM_EMAIL = "Weekly Report Reminder <onboarding@resend.dev>" // This can be customized

serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  try {
    const { email, week_ending_date } = await req.json();

    if (!email) {
      return new Response("Email is required", { status: 400 });
    }

    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${RESEND_API_KEY}`,
      },
      body: JSON.stringify({
        from: FROM_EMAIL,
        to: email,
        subject: `Reminder: Weekly Impact Report Due`,
        html: `
          <p>Hi there,</p>
          <p>This is a friendly reminder that your weekly impact report for the week ending <strong>${week_ending_date}</strong> is due soon.</p>
          <p>Please log in to the reporting tool to complete your submission.</p>
          <p>Thank you!</p>
        `,
      }),
    });

    const data = await res.json();

    return new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    });

  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      headers: { "Content-Type": "application/json" },
      status: 500,
    });
  }
})
