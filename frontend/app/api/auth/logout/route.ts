import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get("refresh_token")?.value;

  await fetch(`${BACKEND}/auth/logout`, {
    method: "POST",
    headers: refreshToken ? { Cookie: `refresh_token=${refreshToken}` } : {},
  });

  const response = NextResponse.json({}, { status: 204 });
  response.cookies.delete("refresh_token");
  return response;
}
