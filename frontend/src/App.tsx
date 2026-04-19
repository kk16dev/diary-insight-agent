// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { BrowserRouter, Link, useLocation } from 'react-router-dom'
import { AuthProvider } from '@/components/auth/AuthProvider'
import AppRoutes from './routes'

function Navigation() {
  const location = useLocation()

  return (
    <nav className="bg-gray-800 text-white p-4 flex gap-4">
      <Link
        to="/"
        className={`px-4 py-2 rounded transition-colors ${
          location.pathname === '/' ? 'bg-gray-600' : 'hover:bg-gray-700'
        }`}
      >
        Chat
      </Link>
      <Link
        to="/drafts"
        className={`px-4 py-2 rounded transition-colors ${
          location.pathname === '/drafts' ? 'bg-gray-600' : 'hover:bg-gray-700'
        }`}
      >
        Drafts
      </Link>
    </nav>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="flex flex-col h-screen">
          <Navigation />
          <div className="flex-1 overflow-hidden">
            <AppRoutes />
          </div>
        </div>
      </AuthProvider>
    </BrowserRouter>
  )
}
