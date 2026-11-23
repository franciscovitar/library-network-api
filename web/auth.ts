import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";

/** No implicit user provisioning: GitHub identities still need DB branch grants. */
export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [GitHub],
  session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
  pages: { signIn: "/login" },
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.staffSubject =
          account.provider === "github" && /^[0-9]+$/.test(account.providerAccountId)
            ? `github:${account.providerAccountId}`
            : undefined;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.staffSubject =
          typeof token.staffSubject === "string" ? token.staffSubject : undefined;
      }
      return session;
    },
  },
});
